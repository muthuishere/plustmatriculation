#!/usr/bin/env python3
"""
Publish the PDF corpus to a public S3 bucket (Hetzner Object Storage by default)
so the GitHub Pages site can link real PDFs instead of local paths.

Why this exists: the corpus is ~1.7 GB and a GitHub Pages site is capped at
1 GB, so the PDFs cannot live in the repo. They go to object storage; the repo
keeps only text, metadata and the scripts to rebuild everything.

    python3 scripts/publish_s3.py create      # make the bucket, set public read
    python3 scripts/publish_s3.py sync        # upload everything missing
    python3 scripts/publish_s3.py sync --dry-run
    python3 scripts/publish_s3.py url         # print the public base URL
    python3 scripts/publish_s3.py verify      # HEAD a few objects over plain HTTPS

Credentials come from the environment and are NEVER written to disk or printed:

    export S3_ACCESS_KEY=...        # or HETZNER_S3_ACCESS_KEY
    export S3_SECRET_KEY=...        # or HETZNER_S3_SECRET_KEY
    export S3_ENDPOINT=https://fsn1.your-objectstorage.com   # fsn1 | nbg1 | hel1
    export S3_BUCKET=tn-plus2-papers

After a successful sync, rebuild the site data so it points at the bucket:

    python3 scripts/questionbank.py --pdf-base "$(python3 scripts/publish_s3.py url)"
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "docs", "assets")

# Hetzner Object Storage locations. The endpoint is auto-detected by asking
# each one whether it holds the bucket, then cached.
LOCATIONS = ["fsn1", "nbg1", "hel1"]
DEFAULT_BUCKET = "tn-plus2-papers"
# Keys land at <prefix>/<exam>/<file>.pdf. The prefix keeps this corpus in its
# own namespace inside a bucket that may hold other things.
PREFIX = os.environ.get("S3_PREFIX", "tn-plus2-papers")
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "docs", "assets", ".aggregate", "s3-endpoint.txt")


def _first(*names: str) -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


def cfg(detect: bool = True) -> dict:
    ak = _first("S3_ACCESS_KEY", "HETZNER_S3_ACCESS_KEY")
    sk = _first("S3_SECRET_KEY", "HETZNER_S3_ACCESS_SECRET", "HETZNER_S3_SECRET_KEY")
    if not ak or not sk:
        sys.exit(
            "missing credentials. Expected in the environment:\n"
            "  HETZNER_S3_ACCESS_KEY / HETZNER_S3_ACCESS_SECRET  (or S3_ACCESS_KEY / S3_SECRET_KEY)\n"
            "Values are read from the environment only — there is deliberately no\n"
            "flag to pass a secret, so it cannot land in your shell history."
        )
    c = {
        "bucket": _first("S3_BUCKET", "HETZNER_PUBLIC_BUCKET") or DEFAULT_BUCKET,
        "env": {**os.environ,
                "AWS_ACCESS_KEY_ID": ak,
                "AWS_SECRET_ACCESS_KEY": sk,
                "AWS_EC2_METADATA_DISABLED": "true",
                # Hetzner rejects writes whose client region disagrees with the
                # location in the endpoint (LocationConstraintConflict).
                "AWS_DEFAULT_REGION": (_first("S3_ENDPOINT", "HETZNER_S3_ENDPOINT")
                                       or "").split("//")[-1].split(".")[0] or "hel1",
                "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
                "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required"},
    }
    ep = _first("S3_ENDPOINT", "HETZNER_S3_ENDPOINT")
    if not ep and os.path.exists(CACHE):
        ep = open(CACHE).read().strip()
    if not ep and detect:
        ep = detect_endpoint(c)
    if not ep:
        # Guessing here would print a plausible-looking public URL for a bucket
        # that is not there, so fail instead.
        sys.exit(f"could not find bucket {c['bucket']!r} in any of {', '.join(LOCATIONS)}.\n"
                 "Set S3_ENDPOINT explicitly if it lives elsewhere.")
    c["endpoint"] = ep.rstrip("/")
    return c


def detect_endpoint(c: dict) -> str:
    """Find the Hetzner location holding the bucket.

    Uses list-buckets rather than head-bucket: Hetzner answers head-bucket with
    403 for a bucket these credentials can still read and write, so head-bucket
    would report "not here" at the right location.
    """
    for loc in LOCATIONS:
        ep = f"https://{loc}.your-objectstorage.com"
        r = subprocess.run(
            ["aws", "--endpoint-url", ep, "s3api", "list-buckets",
             "--query", "Buckets[].Name", "--output", "text"],
            env=c["env"], capture_output=True, text=True)
        if r.returncode == 0 and c["bucket"] in r.stdout.split():
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            open(CACHE, "w").write(ep + "\n")
            print(f"endpoint: {loc} (detected, cached)")
            return ep
    return ""


def aws(c: dict, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["aws", "--endpoint-url", c["endpoint"], *args]
    r = subprocess.run(cmd, env=c["env"], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"aws {' '.join(args[:3])} failed:\n{r.stderr.strip()}")
    return r


def public_base(c: dict) -> str:
    """Hetzner serves virtual-hosted style: https://<bucket>.<host>/<key>"""
    host = c["endpoint"].split("://", 1)[1]
    return f"https://{c['bucket']}.{host}/{PREFIX}"


def cmd_create(args) -> None:
    c = cfg()
    # head-bucket 403s on Hetzner even when the credentials can read and write
    # the bucket, so existence is checked the same way the endpoint is found.
    listing = aws(c, "s3api", "list-buckets", "--query", "Buckets[].Name",
                  "--output", "text", check=False)
    exists = listing.returncode == 0 and c["bucket"] in listing.stdout.split()
    if exists:
        print(f"bucket already exists: {c['bucket']}")
    else:
        aws(c, "s3api", "create-bucket", "--bucket", c["bucket"])
        print(f"created bucket: {c['bucket']}")

    # Public read for objects, but NOT public listing — anyone with a URL can
    # fetch a paper; nobody can enumerate the bucket or write to it.
    policy = (
        '{"Version":"2012-10-17","Statement":[{'
        '"Sid":"PublicReadObjects","Effect":"Allow","Principal":"*",'
        '"Action":["s3:GetObject"],'
        f'"Resource":["arn:aws:s3:::{c["bucket"]}/{PREFIX}/*"]'
        "}]}"
    )
    existing = aws(c, "s3api", "get-bucket-policy", "--bucket", c["bucket"],
                   "--output", "text", check=False)
    if existing.returncode == 0 and "s3:GetObject" in existing.stdout and not args.force_policy:
        print("bucket already has a public-read policy — leaving it alone.")
        print("  (this bucket is shared; replacing the policy would narrow it to")
        print("   this prefix and break every other public object in it.")
        print("   Pass --force-policy only if you really mean to replace it.)")
        print("public base: " + public_base(c))
        return
    r = aws(c, "s3api", "put-bucket-policy", "--bucket", c["bucket"],
            "--policy", policy, check=False)
    if r.returncode == 0:
        print("bucket policy: public read on " + PREFIX + "/*")
    else:
        print("! bucket policy rejected; falling back to per-object ACLs on sync")
        print("  " + r.stderr.strip().splitlines()[-1][:160])
    print("public base: " + public_base(c))


def local_pdfs() -> list[str]:
    out = []
    for base in ("annual", "quarterly", "half-yearly"):
        for root, _d, names in os.walk(os.path.join(ASSETS, base)):
            out.extend(os.path.join(root, n) for n in sorted(names) if n.endswith(".pdf"))
    return sorted(out)


def cmd_sync(args) -> None:
    c = cfg()
    files = local_pdfs()
    size = sum(os.path.getsize(f) for f in files) / 1e9
    print(f"{len(files)} pdfs, {size:.2f} GB -> s3://{c['bucket']}/{PREFIX}/")
    if args.dry_run:
        print("dry run — nothing uploaded")
    problems: list[str] = []
    for base in ("annual", "quarterly", "half-yearly"):
        src = os.path.join(ASSETS, base)
        if not os.path.isdir(src):
            continue
        cmd = ["s3", "sync", src, f"s3://{c['bucket']}/{PREFIX}/{base}/",
               "--exclude", "*", "--include", "*.pdf",
               "--content-type", "application/pdf",
               "--no-progress"]
        if args.acl:
            cmd += ["--acl", "public-read"]
        if args.dry_run:
            cmd += ["--dryrun"]
        # aws-cli 2.34 intermittently dies against Hetzner's Ceph with
        # "argument of type 'NoneType' is not a container or iterable" — the
        # SAME file succeeds on a retry, so it is a transient client bug, not a
        # rejected upload. `s3 sync` is incremental, so each pass only retries
        # what is genuinely still missing.
        for attempt in range(1, args.passes + 1):
            r = aws(c, *cmd, check=False)
            uploaded = sum(1 for l in r.stdout.splitlines() if l.startswith("upload:"))
            failed = sum(1 for l in r.stdout.splitlines() if "upload failed" in l)
            print(f"  {base} pass {attempt}: {uploaded} uploaded, {failed} failed")
            if failed == 0 and r.returncode == 0:
                break
            if args.dry_run:
                break
        else:
            problems.append(base)
    if problems:
        print("! still failing after retries: " + ", ".join(problems))
    print("public base: " + public_base(c))
    if problems and not args.dry_run:
        sys.exit(1)


def cmd_url(args) -> None:
    print(public_base(cfg()))


def cmd_verify(args) -> None:
    c = cfg()
    base = public_base(c)
    files = local_pdfs()
    if not files:
        sys.exit("no local pdfs to check against")
    sample = [files[0], files[len(files) // 2], files[-1]]
    ok = 0
    for f in sample:
        key = os.path.relpath(f, ASSETS)
        url = f"{base}/{key}"
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                same = int(r.headers.get("Content-Length", 0)) == os.path.getsize(f)
                print(f"  {r.status} {'size-match' if same else 'SIZE MISMATCH'}  {key}")
                ok += 1 if (r.status == 200 and same) else 0
        except Exception as exc:                      # noqa: BLE001
            print(f"  FAIL {key}: {exc}")
    print(f"verify: {ok}/{len(sample)} publicly readable at {base}/")
    if ok != len(sample):
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["create", "sync", "url", "verify"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--passes", type=int, default=6,
                    help="retry sync this many times to ride out transient client errors")
    ap.add_argument("--force-policy", action="store_true",
                    help="replace an existing bucket policy (dangerous on a shared bucket)")
    ap.add_argument("--acl", action="store_true",
                    help="also set public-read ACL per object (use if the bucket "
                         "policy was rejected)")
    args = ap.parse_args()
    {"create": cmd_create, "sync": cmd_sync, "url": cmd_url, "verify": cmd_verify}[args.command](args)


if __name__ == "__main__":
    main()
