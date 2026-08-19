#!/usr/bin/env python3
"""
Turn docs/assets/markdown-english/ into a structured question bank.

    python3 scripts/questionbank.py            # build docs/data/questions.json
    python3 scripts/questionbank.py --stats    # build + print a breakdown

TN +2 papers follow a rigid shape, which is what makes this parseable at all:

    PART I    15 x 1 = 15   MCQ, four options
    PART II    6 x 2 = 12   short answer   (answer any 6 of 9)
    PART III   6 x 3 = 18   short answer
    PART IV    5 x 5 = 25   long answer, internal choice ("OR")

So the marks for a question come from the part it sits in, not from the
question itself. We detect part headers, then number-prefixed questions
underneath, then option runs for MCQs.

Every record carries `confidence`: the text comes from PDFs of wildly varying
quality — a clean digital annual paper parses near-perfectly, a 300-dpi OCR of
a photocopied district paper does not. Records are never silently dropped for
being messy; they are labelled so a consumer can filter.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "docs", "assets")
SRC = os.path.join(ASSETS, "markdown-english")
OUT = os.path.join(ROOT, "docs", "data")

PART_MARKS = {"I": 1, "II": 2, "III": 3, "IV": 5, "V": 5}

RE_PART = re.compile(
    r"^\s*(?:PART|SECTION)\s*[-–—:]?\s*([IV]{1,3})\b", re.I)
RE_MARKS_HDR = re.compile(r"(\d{1,2})\s*[xX×]\s*(\d{1,2})\s*=\s*(\d{1,3})")
RE_QNUM = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*(.*)$")
# (a) foo (b) bar ...  /  a) foo b) bar  /  (A) foo (B) bar
RE_OPT = re.compile(r"[（(]?\s*([a-dA-D])\s*[)）.]\s+")
RE_NOISE = re.compile(r"^[\W_]*$")


# Where a block stops being this question and starts being the next thing on
# the page. Extraction interleaves columns, so this happens constantly.
RE_CUT = re.compile(
    r"\s*(?:PART\s*[-–—]?\s*[IVX]+\b"
    r"|SECTION\s*[-–—]?\s*[A-Z0-9IVX]*"
    r"|ANSWER\s+(?:ANY|ALL|IN\s+DETAIL)"
    r"|Answer\s+any\s+\w+\s+of\s+the\s+following"
    r"|\d{1,2}\s*[x×]\s*\d{1,2}\s*=\s*\d{1,3}"
    r"|Marks?\s*:\s*\d"
    r"|Time\s*:\s*\d"
    r"|\(OR\)"
    r"|Reg\.?\s*No)", re.I)


def trim(s: str) -> str:
    """Cut a fragment at the first sign the next section bled into it."""
    m = RE_CUT.search(s)
    if m and m.start() > 0:
        s = s[:m.start()]
    # a stray '...>' or long run of dots is the same bleed, mid-token
    s = re.split(r"\.{3,}|,\.{2,}", s)[0]
    return s.strip(" ,;:-–—")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace(" ", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def meta_from_path(rel: str) -> dict:
    """docs/assets/markdown-english/quarterly/12th-physics-quarterly-2024-salem.md"""
    exam = rel.split(os.sep)[0]
    name = os.path.basename(rel)[:-3]
    parts = name.split("-")
    subject = parts[1] if len(parts) > 1 else "unknown"
    year = next((p for p in parts if re.fullmatch(r"20\d{2}", p)), None)
    tail = parts[-1]
    variant = tail if not re.fullmatch(r"20\d{2}|\d", tail) else None
    return {
        "paper": name,
        "exam": exam,
        "subject": subject,
        "year": year,
        "variant": variant,     # district for term exams, exam month for annual
        "pdf": f"assets/{rel[:-3]}.pdf",
        "is_answer_key": "answer-keys" in rel,
    }


def option_runs(body: str) -> list[list]:
    """All ascending (a)(b)(c)[(d)] label runs in a line of text."""
    hits = list(RE_OPT.finditer(body))
    runs, cur = [], []
    for h in hits:
        lab = h.group(1).lower()
        if not cur:
            if lab == "a":
                cur = [h]
            continue
        expected = chr(ord(cur[-1].group(1).lower()) + 1)
        if lab == expected:
            cur.append(h)
            if lab == "d":
                runs.append(cur)
                cur = []
        elif lab == "a":
            if len(cur) >= 3:
                runs.append(cur)
            cur = [h]
        else:
            if len(cur) >= 3:
                runs.append(cur)
            cur = []
    if len(cur) >= 3:
        runs.append(cur)
    return runs


def split_options(body: str) -> tuple[str, list[str]]:
    """Separate an MCQ stem from its options.

    The PDFs are two-column bilingual, and extraction interleaves the columns,
    so a question routinely arrives as

        (A) …tamil options… (B) … (C) … (D) …  If A and B are invertible …
        (a) …english options… (b) … (c) … (d) …

    i.e. one option run BEFORE the stem and another after. Taking only a
    trailing run (the obvious implementation) found options for 14% of the
    one-mark questions. So: find every run, keep the last complete one as the
    options, and rebuild the stem from the text those runs do not cover.
    """
    runs = option_runs(body)
    if not runs:
        return body, []
    chosen = runs[-1]
    opts = []
    for i, m in enumerate(chosen):
        end = chosen[i + 1].start() if i + 1 < len(chosen) else len(body)
        opts.append(norm(body[m.end():end]))
    opts = [trim(o) for o in opts]
    opts = [o for o in opts if o]

    # stem = everything outside every run
    spans = [(r[0].start(), (len(body) if r is chosen else r[-1].end())) for r in runs]
    keep, last = [], 0
    for a, b in sorted(spans):
        if a > last:
            keep.append(body[last:a])
        last = max(last, b)
    if last < len(body):
        keep.append(body[last:])
    stem = trim(norm(" ".join(keep)))
    if len(opts) < 3 or not stem:
        return body, []
    return stem, opts


# Fragments that mean the block swallowed a section header or a neighbouring
# question — the two-column scramble in district papers does this constantly.
RE_BLEED = re.compile(
    r"(PART\s*[-–—]?\s*[IV]+|SECTION\s*[-–—]?\s*[IVA-D]|ANSWER\s+(ANY|IN\s+DETAIL)"
    r"|Marks\s*:|\(OR\)|Match\s+the\s+following\s*:)", re.I)


def score(rec: dict) -> str:
    """How much to trust this record."""
    t = rec["question"]
    if len(t) < 12:
        return "low"
    letters = sum(c.isalpha() for c in t)
    if letters / max(len(t), 1) < 0.45:
        return "low"                       # symbol/number soup: bad OCR
    words = re.findall(r"[A-Za-z]{2,}", t)
    if len(words) < 3:
        return "low"
    garbled = sum(1 for w in words if not re.search(r"[aeiou]", w.lower()))
    if garbled / max(len(words), 1) > 0.35:
        return "low"
    # A block that ran past its own question is not a question. This is the
    # normal failure for district papers: extraction interleaves the two
    # columns, so one "question" absorbs a section header and its neighbours.
    if len(t) > 600 or len(RE_BLEED.findall(t)) >= 2:
        return "low"
    if len(re.findall(r"(?:^|\s)\d{1,2}[.)]\s", t)) >= 2:
        return "low"                       # more than one question number inside
    if rec["marks"] == 1 and not rec["options"]:
        return "medium"                    # an MCQ whose options did not parse
    # "High" is the pool practice draws from, so it has to mean a question a
    # student can actually answer on sight: real options, a stem long enough to
    # be a question, and none of the pipe/underscore debris a scanned table
    # leaves behind.
    if rec["marks"] and rec["options"]:
        words = re.findall(r"[A-Za-z]{2,}", t)
        clean = (len(words) >= 6
                 and not re.search(r"[|_]{2,}|\|\s*\|", t)
                 and re.match(r"^[A-Z(]", t.strip())
                 and all(len(o) > 1 for o in rec["options"]))
        return "high" if clean else "medium"
    return "medium" if rec["marks"] else "low"


def parse_file(path: str, rel: str) -> list[dict]:
    meta = meta_from_path(rel)
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()

    part, marks = None, None
    out: list[dict] = []
    cur: dict | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal cur, buf
        if cur is None:
            return
        body = norm(" ".join(buf))
        stem, opts = split_options(body)
        rec = dict(meta)
        rec.update({
            "number": cur["number"],
            "part": part,
            "marks": marks,
            "question": trim(norm(stem)),
            "options": opts,
        })
        rec["id"] = f"{meta['paper']}#{cur['number']}"
        rec["confidence"] = score(rec)
        if rec["question"]:
            out.append(rec)
        cur, buf = None, []

    for raw in lines:
        line = norm(raw)
        if not line or RE_NOISE.match(line) or line.startswith(("#", ">", "<!--")):
            continue

        m = RE_PART.match(line)
        if m:
            flush()
            part = m.group(1).upper()
            marks = PART_MARKS.get(part)
            mh = RE_MARKS_HDR.search(line)
            if mh:                          # "6 x 2 = 12" is authoritative
                marks = int(mh.group(2))
            continue
        mh = RE_MARKS_HDR.search(line)
        if mh and len(line) < 40:
            marks = int(mh.group(2))
            continue

        q = RE_QNUM.match(line)
        if q:
            n = int(q.group(1))
            # a new question must not go backwards (page numbers, option counts)
            if cur is None or n > cur["number"] or n == 1:
                flush()
                cur = {"number": n}
                buf = [q.group(2)]
                continue
        if cur is not None:
            buf.append(line)
    flush()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low")
    ap.add_argument("--pdf-base", default=os.environ.get("PDF_BASE_URL", ""),
                    help="public base URL for the PDFs (e.g. the S3 bucket from\n"
                         "publish_s3.py url). Without it, papers.json keeps the\n"
                         "local relative path, which only resolves when you serve\n"
                         "docs/ yourself.")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        raise SystemExit(f"{SRC} missing — run `python3 scripts/aggregate.py clean` first")

    # url -> file map, so the site can fall back to the original host when the
    # PDFs are not committed (they are ~1 GB; GitHub Pages caps a site at 1 GB)
    src_by_path: dict[str, str] = {}
    mpath = os.path.join(ASSETS, ".aggregate", "manifest.json")
    if os.path.exists(mpath):
        for url, meta in json.load(open(mpath)).items():
            src_by_path[meta["path"].replace("docs/", "", 1)] = url

    rank = {"low": 0, "medium": 1, "high": 2}
    records: list[dict] = []
    papers: list[dict] = []
    for root, _d, names in os.walk(SRC):
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, SRC)
            recs = parse_file(path, rel)
            records.extend(recs)
            p = meta_from_path(rel)
            p["questions"] = len(recs)
            p["source"] = src_by_path.get(p["pdf"])
            if args.pdf_base:
                p["pdf"] = args.pdf_base.rstrip("/") + "/" + p["pdf"].replace("assets/", "", 1)
                p["hosted"] = True
            papers.append(p)

    records = [r for r in records if rank[r["confidence"]] >= rank[args.min_confidence]]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "questions.json"), "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT, "papers.json"), "w", encoding="utf-8") as fh:
        json.dump(sorted(papers, key=lambda p: (p["exam"], p["subject"], p["year"] or "")),
                  fh, ensure_ascii=False, indent=1)

    print(f"questions: {len(records):,} from {len(papers)} papers -> docs/data/questions.json")
    if args.stats:
        for key in ("subject", "exam", "year", "confidence", "marks"):
            c = collections.Counter(r.get(key) for r in records)
            print(f"  by {key}: {dict(c.most_common(12))}")
        mcq = sum(1 for r in records if r["options"])
        print(f"  with parsed options: {mcq:,} ({mcq / max(len(records), 1):.0%})")


if __name__ == "__main__":
    main()
