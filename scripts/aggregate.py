#!/usr/bin/env python3
"""
Aggregate TN +2 (HSC) science question papers into docs/assets/.

Pipeline (each stage is idempotent and resumable):

    discover  crawl the source hubs -> .aggregate/links.tsv
    fetch     download every link -> docs/assets/<exam>/[answer-keys/]*.pdf
    dedupe    remove byte-identical PDFs (DRY RUN unless --apply)
    markdown  MarkItDown every PDF -> docs/assets/markdown/<same path>.md
    ocr       OCR the PDFs that have no usable text layer (tesseract, eng)
    clean     strip watermarks + legacy-Tamil mojibake -> markdown-english/
    index     regenerate docs/assets/README.md with the coverage matrix
    all       run every stage in order

Usage:
    python3 scripts/aggregate.py all
    python3 scripts/aggregate.py fetch --limit 20
    python3 scripts/aggregate.py dedupe --apply

State lives in docs/assets/.aggregate/manifest.json: url -> {path, sha256,
source, bytes}. Re-runs skip anything already present, so this is safe to
run repeatedly and cheap to run after adding a new source hub.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "docs", "assets")
STATE = os.path.join(ASSETS, ".aggregate")
LINKS = os.path.join(STATE, "links.tsv")
MANIFEST = os.path.join(STATE, "manifest.json")
CACHE = os.path.join(STATE, "pages")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# --------------------------------------------------------------------------
# What we collect
# --------------------------------------------------------------------------

# Canonical subject names. Order matters: longest/most specific first, because
# "bio-botany" must win over "botany" and "biology".
SUBJECT_ALIASES = [
    ("bio-botany", "botany"),
    ("bio-zoology", "zoology"),
    ("mathematics", "maths"),
    ("chemistry", "chemistry"),
    ("physics", "physics"),
    ("botany", "botany"),
    ("zoology", "zoology"),
    ("biology", "biology"),
    ("maths", "maths"),
]
SUBJECTS = ["physics", "chemistry", "maths", "biology", "botany", "zoology"]

# TN districts, used to label district-set quarterly / half-yearly papers.
DISTRICTS = [
    "ariyalur", "chengalpattu", "chennai", "coimbatore", "cuddalore",
    "dharmapuri", "dindigul", "dindugal", "erode", "kallakurichi",
    "kancheepuram", "kanchipuram", "kanyakumari", "karaikal", "karur",
    "krishnagiri", "madurai", "mayiladuthurai", "nagapattinam", "namakkal",
    "nilgiris", "perambalur", "pudukkottai", "pudhukottai", "ramanathapuram",
    "ranipet", "salem", "sivaganga", "sivagangai", "sivakasi", "sivagasi",
    "tenkasi", "thenkasi", "thanjavur", "theni", "thoothukudi", "toothukudi",
    "tuticorin", "thiruvallur", "tiruvallur", "thiruvarur", "tiruvarur",
    "tirunelveli", "tirupathur", "tirupattur", "tiruppur", "tirupur",
    "tiruvannamalai", "thiruvannamalai", "trichy", "tiruchirappalli",
    "vellore", "viluppuram", "villupuram", "virudhunagar",
]

# Source hubs. Add a URL here and re-run `discover fetch` to extend coverage.
SOURCES = {
    # Annual / public-exam papers. One bilingual paper statewide per subject.
    # The index page links one post per subject-year; each post holds a Drive link.
    "annual_index": [
        "https://www.tamilaruvi.in/p/12th-public-exam-original-question.html",
    ],
    # Quarterly + half-yearly. District-set, so many papers per subject-year.
    # 2022-2024 are direct PDFs on padasalai.info; 2025+ moved to Google Drive
    # links whose anchor text is generic ("PDF Download Here"), so those are
    # classified from the surrounding page text instead of the filename.
    "term_hubs": [
        "https://www.padasalai.net/2023/10/Plus-Two-12th-Half-Yearly-Exam-2023-2024-Question-Papers-Answer-Keys-Time-Table-PDF-Download.html",
        "https://www.padasalai.net/2024/08/Plus-Two-12th-Half-Yearly-Exam-Question-Papers-2024-2025-Answer-Keys-Time-Table-PDF-Download.html",
        "https://www.padasalai.net/2025/07/12th-half-yearly-question-papers-2025-answer-keys-download-plus-two-class-time-table-2026.html",
        "https://www.padasalai.net/2026/05/12th-standard-half-yearly-question-papers-2026-2027-answer-keys-download-plus-two-class-time-table.html",
        "https://www.padasalai.net/2025/06/12th-quarterly-exam-question-papers-2025-answer-keys-time-table-download-plus-two.html",
        "https://www.padasalai.co.in/p/12th-quarterly-exam-question-papers-and.html",
        "https://www.padasalai.net/2025/09/quarterly-exam-2025-questions-paper_22.html",
        # per-year quarterly hubs
        "https://www.padasalai.net/2022/08/plus-two-12th-quarterly-exam-question-paper-answer-keys-pdf-download-2022-2023.html",
        "https://www.padasalai.net/2023/07/12th-quarterly-exam-2023-question-papers-answer-keys-time-table-download-plus-two.html",
        "https://www.padasalai.net/2024/07/12th-quarterly-exam-question-papers-2024-answer-keys-time-table-download-plus-two.html",
    ]
    + [
        # per-subject quarterly pages accumulate several years of links each
        f"https://www.padasalai.net/{y}/{m}/12th-{s}-Quarterly-Exam-Question-Papers-{yr}-Answer-Keys-English-Medium-Download.html"
        for s in ["Physics", "Chemistry", "Maths", "Biology", "Botany", "Zoology"]
        for y, m, yr in [("2025", "09", "2025"), ("2024", "07", "2024")]
    ],
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def load_manifest() -> dict:
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            return json.load(fh)
    return {}


def save_manifest(m: dict) -> None:
    os.makedirs(STATE, exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(m, fh, indent=1, sort_keys=True)
    os.replace(tmp, MANIFEST)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url: str, cache: bool = True, timeout: int = 60) -> str:
    """Fetch an HTML page, cached on disk so re-running discover is free."""
    os.makedirs(CACHE, exist_ok=True)
    key = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".html")
    if cache and os.path.exists(key) and os.path.getsize(key) > 0:
        return open(key, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log(f"  ! fetch failed {url}: {exc}")
        return ""
    with open(key, "w", encoding="utf-8") as fh:
        fh.write(body)
    return body


def strip_tags(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    return html.unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", s)))


def classify(text: str, *, filename: bool) -> tuple | None:
    """(exam, subject, year, kind, tag) from a filename or page context, or None."""
    low = text.lower()
    if re.search(r"(^|[^0-9])(11th|10th|9th)", low):
        return None
    if "12th" not in low and "plus two" not in low:
        return None

    subject = None
    for alias, canon in SUBJECT_ALIASES:
        if alias in low:
            subject = canon
            break
    if subject is None:
        return None

    if "quarterly" in low:
        exam = "quarterly"
    elif re.search(r"half[\s_-]?yearly", low):
        exam = "half-yearly"
    elif filename:
        return None
    else:
        return None

    # Medium: annual papers are bilingual; term papers are printed per medium.
    if "tamil medium" in low or "tamil-medium" in low or "urdu medium" in low:
        return None
    if filename and not ("english-medium" in low or re.search(r"(^|[-_])em[-_]", low)):
        return None

    year = re.search(r"20\d{2}", low)
    year = year.group(0) if year else "na"
    kind = "answer-key" if re.search(r"answer[\s_-]*keys?", low) else "question-paper"

    tag = next((d for d in DISTRICTS if d in low), None)
    if tag is None:
        tag = "model" if "model" in low else "set"
    return exam, subject, year, kind, tag


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------

def stage_discover(args) -> None:
    """Crawl the source hubs and write links.tsv."""
    os.makedirs(STATE, exist_ok=True)
    rows: dict[str, tuple] = {}   # url -> (exam, subject, year, kind, tag, source)

    # --- annual: index page -> one post per subject-year -> a Drive link ------
    for hub in SOURCES["annual_index"]:
        page = get(hub, cache=not args.refresh)
        posts = sorted(set(re.findall(
            r'href="(https://www\.tamilaruvi\.in/20\d{2}/\d{2}/12th-[^"]+\.html)"', page)))
        posts = [p for p in posts
                 if re.search(r"12th-(physics|chemistry|maths|biology|botany|zoology)[-a-z]*-", p)
                 and not re.search(r"business|bussiness|micro|bio-chemistry", p)]
        log(f"discover: {len(posts)} annual posts from {hub}")
        for post in posts:
            body = get(post, cache=not args.refresh)
            m = re.search(r"drive\.google\.com/file/d/([\w-]+)", body)
            if not m:
                log(f"  ! no drive link on {post}")
                continue
            slug = os.path.basename(post)[:-5]
            subject = next((c for a, c in SUBJECT_ALIASES if f"12th-{a}-" in slug), None)
            if subject is None:
                continue
            sess = re.search(
                r"(january|february|march|april|may|june|july|august|september|"
                r"october|november|december)-(20\d{2})", slug)
            if sess:
                month, year = sess.group(1), sess.group(2)
            else:
                month, year = "", (re.search(r"/(20\d{2})/", post) or ["", "na"])[1]
            tag = month or "set"
            url = f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
            rows[url] = ("annual", subject, year, "question-paper", tag, post)

    # --- quarterly / half-yearly --------------------------------------------
    for hub in SOURCES["term_hubs"]:
        page = get(hub, cache=not args.refresh)
        if not page:
            continue
        n0 = len(rows)

        # (a) direct PDFs — everything we need is in the filename
        for url in sorted(set(re.findall(
                r"https?://[\w.]*padasalai[\w.]*/wp-content/uploads/[^\"'\s]+\.pdf", page))):
            got = classify(os.path.basename(url), filename=True)
            if got:
                rows[url] = got + (hub,)

        # (b) Drive links — anchor text is generic, so read the text before it
        marked = re.sub(
            r'<a\b[^>]*href="[^"]*drive\.google\.com/file/d/([\w-]+)[^"]*"[^>]*>.*?</a>',
            lambda m: f" @@D:{m.group(1)}@@ ", page, flags=re.S | re.I)
        text = strip_tags(marked)
        for m in re.finditer(r"@@D:([\w-]+)@@", text):
            ctx = re.sub(r"@@D:[\w-]+@@", "|", text[max(0, m.start() - 400):m.start()])
            tail = ctx.strip()[-260:]
            # the last cell/row before the link describes it; fall back to wider context
            seg = tail.rsplit("|", 1)[-1]
            got = classify(seg if len(seg) > 40 else tail, filename=False)
            if not got:
                continue
            url = (f"https://drive.usercontent.google.com/download?"
                   f"id={m.group(1)}&export=download&confirm=t")
            rows.setdefault(url, got + (hub,))
        log(f"discover: +{len(rows) - n0} from {hub.split('/')[-1][:60]}")

    with open(LINKS, "w") as fh:
        for url, (exam, subject, year, kind, tag, src) in sorted(rows.items(), key=lambda kv: kv[1]):
            fh.write(f"{exam}\t{subject}\t{year}\t{kind}\t{tag}\t{url}\t{src}\n")
    by_exam = collections.Counter(v[0] for v in rows.values())
    log(f"discover: {len(rows)} links -> {LINKS}  {dict(by_exam)}")


def target_path(exam: str, subject: str, year: str, kind: str, tag: str, seen: collections.Counter) -> str:
    sub = exam if kind == "question-paper" else os.path.join(exam, "answer-keys")
    stem = f"12th-{subject}-{exam}-{year}" if exam != "annual" else f"12th-{subject}-{year}"
    if tag and tag != "set":
        stem += f"-{tag}"
    seen[stem] += 1
    if seen[stem] > 1:
        stem += f"-{seen[stem]}"
    return os.path.join(ASSETS, sub, stem + ".pdf")


def stage_fetch(args) -> None:
    """Download every link in links.tsv that we do not already have."""
    if not os.path.exists(LINKS):
        sys.exit(f"no {LINKS} — run `discover` first")
    manifest = load_manifest()
    # links.tsv is written in a stable sort order, so recomputing names from
    # scratch every run is deterministic — the same row always claims the same
    # filename, which is what makes `fetch` resumable and lets it adopt files
    # that are already on disk.
    seen: collections.Counter = collections.Counter()

    ok = skip = adopt = fail = 0
    rows = [l.rstrip("\n").split("\t") for l in open(LINKS) if l.strip()]
    for exam, subject, year, kind, tag, url, src in rows:
        if args.limit and ok >= args.limit:
            break
        path = target_path(exam, subject, year, kind, tag, seen)
        prev = manifest.get(url)
        if prev and os.path.exists(os.path.join(ROOT, prev["path"])):
            skip += 1
            continue
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            # already downloaded by an earlier run — record it, don't refetch
            manifest[url] = {"path": os.path.relpath(path, ROOT), "sha256": sha256(path),
                             "bytes": os.path.getsize(path), "source": src}
            adopt += 1
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        rc = subprocess.run(
            ["curl", "-sSL", "-A", UA, "--max-time", "120", "-o", tmp, url],
            capture_output=True).returncode
        good = (rc == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1000
                and open(tmp, "rb").read(4) == b"%PDF")
        if not good:
            if os.path.exists(tmp):
                os.remove(tmp)
            fail += 1
            continue
        os.replace(tmp, path)
        manifest[url] = {
            "path": os.path.relpath(path, ROOT),
            "sha256": sha256(path),
            "bytes": os.path.getsize(path),
            "source": src,
        }
        ok += 1
        if ok % 25 == 0:
            save_manifest(manifest)
            log(f"  fetched {ok} (skip {skip}, fail {fail})")
        time.sleep(args.delay)
    save_manifest(manifest)
    log(f"fetch: downloaded={ok} adopted={adopt} known={skip} failed={fail}")


def stage_dedupe(args) -> None:
    """Remove byte-identical PDFs.

    Deliberately paranoid: builds ONE canonical set of real paths, and asserts a
    file can never be its own duplicate. (An earlier version used two
    overlapping globs, listed every top-level file twice, and deleted each one
    as a 'duplicate' of itself.) Dry run unless --apply.
    """
    files = []
    for base in ("annual", "quarterly", "half-yearly"):
        d = os.path.join(ASSETS, base)
        for root, _dirs, names in os.walk(d):
            files.extend(os.path.join(root, n) for n in names if n.endswith(".pdf"))
    files = sorted({os.path.realpath(f) for f in files})

    first: dict[str, str] = {}
    dupes: list[tuple[str, str]] = []
    for f in files:
        h = sha256(f)
        if h in first:
            assert first[h] != f, f"refusing to delete {f} as a duplicate of itself"
            dupes.append((f, first[h]))
        else:
            first[h] = f
    log(f"dedupe: {len(files)} pdfs, {len(dupes)} byte-identical duplicates")
    for dup, orig in dupes[:20]:
        log(f"  {os.path.relpath(dup, ASSETS)}  ==  {os.path.relpath(orig, ASSETS)}")
    if not args.apply:
        log("dedupe: DRY RUN — pass --apply to delete")
        return
    manifest = load_manifest()
    gone = {os.path.relpath(d, ROOT) for d, _ in dupes}
    for dup, _ in dupes:
        os.remove(dup)
    for url in [u for u, m in manifest.items() if m["path"] in gone]:
        del manifest[url]
    save_manifest(manifest)
    log(f"dedupe: removed {len(dupes)}")


def md_path(pdf: str) -> str:
    return os.path.join(ASSETS, "markdown", os.path.relpath(pdf, ASSETS)[:-4] + ".md")


def all_pdfs() -> list[str]:
    out = []
    for base in ("annual", "quarterly", "half-yearly"):
        for root, _d, names in os.walk(os.path.join(ASSETS, base)):
            out.extend(os.path.join(root, n) for n in sorted(names) if n.endswith(".pdf"))
    return sorted(out)


def stage_markdown(args) -> None:
    """MarkItDown every PDF; drop .md files whose PDF is gone."""
    if not shutil.which("markitdown"):
        sys.exit("markitdown not on PATH (pipx install markitdown / uv tool install markitdown)")
    made = 0
    for pdf in all_pdfs():
        out = md_path(pdf)
        if os.path.exists(out) and os.path.getsize(out) > 0 and not args.force:
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        # MarkItDown can pathologically hang on a malformed scan (one file ran
        # 34 min / 5 GB before being killed). Cap it, fall back to pdftotext,
        # and let the `ocr` stage rescue whatever is still empty.
        body = b""
        try:
            r = subprocess.run(["markitdown", pdf], capture_output=True, timeout=args.timeout)
            body = r.stdout
        except subprocess.TimeoutExpired:
            log(f"  ! markitdown timed out, falling back: {os.path.relpath(pdf, ASSETS)}")
        if len(body.split()) < 40 and shutil.which("pdftotext"):
            try:
                r = subprocess.run(["pdftotext", "-q", pdf, "-"],
                                   capture_output=True, timeout=args.timeout)
                if len(r.stdout.split()) > len(body.split()):
                    body = r.stdout
            except subprocess.TimeoutExpired:
                pass
        with open(out, "wb") as fh:
            fh.write(body)
        made += 1
        if made % 50 == 0:
            log(f"  markdown {made}")
    # orphans
    orphan = 0
    mdroot = os.path.join(ASSETS, "markdown")
    for root, _d, names in os.walk(mdroot):
        for n in names:
            if not n.endswith(".md"):
                continue
            m = os.path.join(root, n)
            if not os.path.exists(os.path.join(ASSETS, os.path.relpath(m, mdroot)[:-3] + ".pdf")):
                os.remove(m)
                orphan += 1
    log(f"markdown: converted {made}, removed {orphan} orphans, "
        f"{sum(len([x for x in n if x.endswith('.md')]) for _r, _d, n in os.walk(mdroot))} total")


def text_len(path: str) -> int:
    try:
        return len("".join(open(path, encoding="utf-8", errors="replace").read().split()))
    except OSError:
        return 0


def stage_ocr(args) -> None:
    """OCR any PDF whose extracted text is too thin to be the real paper."""
    for tool in ("pdftoppm", "tesseract"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not on PATH (brew install poppler tesseract)")
    todo = [p for p in all_pdfs()
            if text_len(md_path(p)) < args.min_chars
            and "recovered by OCR" not in open(md_path(p), encoding="utf-8", errors="replace").read()[:200]]
    log(f"ocr: {len(todo)} pdfs below {args.min_chars} chars")
    tmp = os.path.join(STATE, "ocrtmp")
    done = 0
    for pdf in todo:
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        subprocess.run(["pdftoppm", "-png", "-r", str(args.dpi), pdf, os.path.join(tmp, "pg")],
                       capture_output=True)
        chunks = []
        for img in sorted(os.listdir(tmp)):
            if not img.endswith(".png"):
                continue
            r = subprocess.run(["tesseract", os.path.join(tmp, img), "stdout", "-l", "eng",
                                "--psm", "4"], capture_output=True)
            chunks.append(r.stdout.decode("utf-8", "replace"))
        body = "\n\n".join(chunks).strip()
        if body:
            with open(md_path(pdf), "w", encoding="utf-8") as fh:
                fh.write("<!-- text recovered by OCR (tesseract, eng); "
                         "source PDF has no text layer -->\n\n" + body + "\n")
            done += 1
        if done and done % 20 == 0:
            log(f"  ocr {done}/{len(todo)}")
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"ocr: recovered {done}")


# Watermarks the sources stamp across every page.
# Mirror-site watermarks stamped across the scans. CBSEtips.in is one of them —
# it is the mirror's domain, not CBSE content: every paper here is Tamil Nadu
# State Board. Left unstripped it makes the corpus look like it has CBSE in it.
WATERMARK = re.compile(
    r"(https?://)?(www\.)?(t\.me/)?"
    r"(tamilaruvi|padasalai|trbtnpsc|kalvi|cbsetips|tntextbooks|surabooks)\S*", re.I)


def ok_nonascii(ch: str) -> bool:
    """True for maths/typography, false for legacy-Tamil mojibake."""
    o = ord(ch)
    return (0x0370 <= o <= 0x03FF or 0x2000 <= o <= 0x20CF
            or 0x2100 <= o <= 0x23FF or 0x25A0 <= o <= 0x25FF
            or ch in "°±×÷µΩ√∞·⋅‰")


def is_english(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    bad = sum(1 for c in s if not c.isascii() and not ok_nonascii(c))
    if bad / max(len(s), 1) > 0.06:
        return False
    words = re.findall(r"[A-Za-z]{2,}", s)
    if len(words) > 2 and sum(1 for w in words if re.search(r"[aeiouAEIOU]", w)) / len(words) < 0.4:
        return False   # consonant soup = transliterated Tamil glyphs
    return True


def stage_clean(args) -> None:
    """markdown/ -> markdown-english/: watermarks out, Tamil column out."""
    src = os.path.join(ASSETS, "markdown")
    dst = os.path.join(ASSETS, "markdown-english")
    shutil.rmtree(dst, ignore_errors=True)
    n_in = n_out = files = 0
    for root, _d, names in os.walk(src):
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, src)
            raw = open(p, encoding="utf-8", errors="replace").read()
            n_in += len(raw)
            kept, blank = [], 0
            for ln in raw.splitlines():
                ln = WATERMARK.sub("", ln).rstrip()
                if len(ln) > 200 and " " not in ln.strip():
                    continue           # a de-watermarked run of glued junk
                if not is_english(ln):
                    continue
                if ln.strip():
                    blank = 0
                    kept.append(ln)
                elif blank == 0:
                    blank = 1
                    kept.append("")
            body = "\n".join(kept).strip() + "\n"
            parts = name[:-3].split("-")
            subject = parts[1] if len(parts) > 1 else "?"
            exam = rel.split(os.sep)[0]
            header = (f"# TN +2 {subject.title()} — {exam.replace('-', ' ').title()} "
                      f"({name[:-3]})\n\n"
                      f"> Source PDF: `docs/assets/{rel[:-3]}.pdf`\n"
                      f"> English text only; Tamil column and site watermarks stripped.\n\n")
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(header + body)
            n_out += len(body)
            files += 1
    log(f"clean: {files} files, {n_in:,} -> {n_out:,} chars ({n_out / max(n_in, 1):.0%} kept)")


def stage_index(args) -> None:
    """Regenerate docs/assets/README.md."""
    grid: dict = collections.defaultdict(collections.Counter)
    years: set = set()
    for pdf in all_pdfs():
        rel = os.path.relpath(pdf, ASSETS)
        exam = rel.split(os.sep)[0]
        kind = "AK" if "answer-keys" in rel else "QP"
        parts = os.path.basename(pdf)[:-4].split("-")
        subject = parts[1]
        y = re.search(r"(20\d{2}|na)", os.path.basename(pdf))
        y = y.group(1) if y else "na"
        years.add(y)
        grid[(exam, subject)][(y, kind)] += 1
    ylist = sorted(years)

    def table(exam: str) -> str:
        head = "| Subject | " + " | ".join(ylist) + " | total |"
        rule = "|---" * (len(ylist) + 2) + "|"
        lines = [head, rule]
        for s in SUBJECTS:
            c = grid[(exam, s)]
            cells = []
            for y in ylist:
                qp, ak = c[(y, "QP")], c[(y, "AK")]
                cells.append(f"{qp}" + (f" +{ak}ak" if ak else "") if qp or ak else "—")
            lines.append(f"| {s.title()} | " + " | ".join(cells) + f" | {sum(c.values())} |")
        return "\n".join(lines)

    n_pdf = len(all_pdfs())
    n_md = sum(1 for _r, _d, n in os.walk(os.path.join(ASSETS, "markdown")) for x in n if x.endswith(".md"))
    ocr = sum(1 for p in all_pdfs()
              if "recovered by OCR" in open(md_path(p), encoding="utf-8", errors="replace").read()[:200])
    size = sum(os.path.getsize(p) for p in all_pdfs()) / 1e6

    doc = f"""# TN +2 (HSC 2nd Year) Question Papers — Science

Tamil Nadu Class 12 papers for **Physics, Chemistry, Maths, Biology, Botany, Zoology**.
{n_pdf} PDFs ({size:.0f} MB), {n_md} markdown conversions ({ocr} of them recovered by OCR).

Regenerate everything with `python3 scripts/aggregate.py all`.

## Layout

```
docs/assets/
├── annual/            public (board) exam — ONE bilingual paper statewide per subject
├── quarterly/         September term exam — set per DISTRICT, so many per subject-year
│   └── answer-keys/
├── half-yearly/       December term exam — also district-set
│   └── answer-keys/
├── markdown/          raw MarkItDown output, mirroring the tree above
├── markdown-english/  same text, watermarks + Tamil column stripped
└── .aggregate/        crawl state: links.tsv, manifest.json (url -> file, sha256)
```

Filenames: `12th-<subject>-<year>-<month>.pdf` (annual) and
`12th-<subject>-<exam>-<year>-<district>.pdf` (term exams).

## Coverage

### Annual (public exam)

{table('annual')}

### Quarterly

{table('quarterly')}

### Half-yearly

{table('half-yearly')}

`+Nak` = N answer keys alongside the question papers.

## Things that will otherwise surprise you

- **Annual papers are bilingual, term papers are not.** The board prints one paper carrying
  both languages ("தமிழ் மற்றும் ஆங்கில வழி / Tamil & English Version"), so the annual set
  serves English medium directly. District quarterly/half-yearly papers are printed per
  medium — only the English-medium ones are collected here.
- **There is no single quarterly or half-yearly paper for a year.** Each district frames its
  own, which is why one subject-year holds 20+ files. The district is in the filename.
- **2021 is empty and that is correct** — no term exams were held that COVID year, and 2020
  is sparse for the same reason. Physics April 2020 does not exist either; that sitting was
  cancelled mid-lockdown, so the September 2020 supplementary is the 2020 Physics paper.
- **The Tamil in `markdown/` is mojibake.** The board typesets Tamil in a legacy 8-bit font,
  so it extracts as Latin garbage (`C¯Ø¤¯À` = `இயற்பியல்`). The English extracts cleanly,
  maths symbols included. `markdown-english/` drops the Tamil rather than pretending to fix it.
- **Reading order follows the PDF's two columns**, so an MCQ's options can appear before its
  question stem. Fine for search; needs a reflow pass to become a clean question bank.

Sources: [tamilaruvi.in](https://www.tamilaruvi.in/p/12th-public-exam-original-question.html)
(annual), [padasalai.net](https://www.padasalai.net) (term exams) — both mirror the DGE
originals. Official portal: [dge.tn.gov.in](https://dge.tn.gov.in).
"""
    with open(os.path.join(ASSETS, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(doc)
    log(f"index: wrote docs/assets/README.md ({n_pdf} pdfs, {n_md} md)")


STAGES = {
    "discover": stage_discover,
    "fetch": stage_fetch,
    "dedupe": stage_dedupe,
    "markdown": stage_markdown,
    "ocr": stage_ocr,
    "clean": stage_clean,
    "index": stage_index,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=list(STAGES) + ["all"])
    ap.add_argument("--apply", action="store_true", help="dedupe: actually delete")
    ap.add_argument("--force", action="store_true", help="markdown: reconvert existing")
    ap.add_argument("--refresh", action="store_true", help="discover: bypass the page cache")
    ap.add_argument("--limit", type=int, default=0, help="fetch: stop after N new files")
    ap.add_argument("--delay", type=float, default=0.2, help="fetch: seconds between requests")
    ap.add_argument("--min-chars", type=int, default=500, help="ocr: threshold for 'no text layer'")
    ap.add_argument("--dpi", type=int, default=300, help="ocr: rasterisation dpi")
    ap.add_argument("--timeout", type=int, default=120,
                    help="markdown: seconds before giving up on one PDF")
    args = ap.parse_args()

    os.makedirs(ASSETS, exist_ok=True)
    order = ["discover", "fetch", "dedupe", "markdown", "ocr", "clean", "index"]
    for name in (order if args.stage == "all" else [args.stage]):
        log(f"\n=== {name} ===")
        STAGES[name](args)


if __name__ == "__main__":
    main()
