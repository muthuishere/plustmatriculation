# plustmatriculation

Tamil Nadu **+2 (HSC, Class 12) science question papers**, aggregated, converted to text,
parsed into a question bank, and published as a static site.

Subjects: Physics · Chemistry · Maths · Biology · Botany · Zoology.
Exams: **annual** (statewide board exam), **quarterly** (September), **half-yearly** (December).

```
scripts/aggregate.py     crawl -> download -> dedupe -> markdown -> OCR -> clean -> index
scripts/questionbank.py  markdown-english/ -> docs/data/questions.json
docs/index.html          the GitHub Pages site (papers browser, question bank, practice)
docs/assets/             the corpus (PDFs are gitignored; see "Publishing")
Taskfile.yml             task, task fetch, task dedupe:apply, task stats, task deps
```

## Quick start

```bash
task deps          # brew install poppler tesseract; uv tool install markitdown
task               # full pipeline: aggregate.py all
python3 scripts/questionbank.py --stats
python3 -m http.server -d docs 8000   # then open http://localhost:8000
```

Every stage is idempotent — re-running skips what already exists, so an interrupted run
resumes rather than restarts.

## How the aggregation works

`discover` crawls a list of source hubs into `.aggregate/links.tsv`; `fetch` downloads
anything not already recorded in `.aggregate/manifest.json` (url → path, sha256, source page).
Add a hub URL to `SOURCES` in `scripts/aggregate.py` and re-run `task discover && task fetch`
to widen coverage.

Two link formats have to be handled, because the sources changed hosting mid-stream:

- **2022–2024** are direct PDFs whose filenames carry everything
  (`12th-Physics-EM-Quarterly-Exam-2023-Original-Question-Paper-Salem-District-English-Medium.pdf`).
- **2025 onward** moved to Google Drive links whose anchor text is just "PDF Download Here",
  so subject, exam, year and district are recovered from the surrounding page text instead.

## Things worth knowing about this corpus

- **Annual papers are bilingual; term papers are not.** The board prints one paper carrying
  Tamil and English side by side, so the annual set serves English medium directly. District
  quarterly/half-yearly papers are printed per medium — only English-medium ones are collected.
- **There is no single quarterly or half-yearly paper for a year.** Each district frames its
  own, so one subject-year holds 20+ variants. The district is in the filename.
- **2021 is empty, and that is correct** — no term exams were held that COVID year. 2020 is
  sparse for the same reason, and Physics April 2020 does not exist at all: that sitting was
  cancelled mid-lockdown, so the September 2020 supplementary is the 2020 Physics paper.
- **The Tamil extracts as mojibake.** The board typesets Tamil in a legacy 8-bit font, so it
  comes out as Latin garbage (`C¯Ø¤¯À` = `இயற்பியல்`). Fixing it needs glyph-level
  transcoding, not a better extractor. English extracts cleanly, maths symbols included, so
  `markdown-english/` drops the Tamil rather than pretending to fix it.
- **Roughly a third of the PDFs are image-only scans** and go through tesseract. Their text is
  usable for search but noisy — which is what the question bank's `confidence` field tracks.
- **Reading order follows the PDF's two columns**, so an MCQ's options can appear before its
  stem in the raw text. The question-bank parser reassembles them; the raw markdown does not.

## Question bank

`questionbank.py` exploits the fixed shape of a TN +2 paper — Part I is 15×1 MCQs, Part II
6×2, Part III 6×3, Part IV 5×5 — so a question's marks come from the part it sits under.
Every record is labelled `high` / `medium` / `low` confidence rather than dropped, so you can
filter instead of losing coverage. Records carry subject, exam, year, district, part, marks,
options and the source PDF.

```bash
python3 scripts/questionbank.py --stats
python3 scripts/questionbank.py --min-confidence high   # strict build
```

## Publishing

The site is `docs/` — set GitHub Pages to "deploy from branch, /docs" and it serves as is
(`.nojekyll` is present so nothing is filtered).

**The PDFs are deliberately not committed.** They are ~1.1 GB and a Pages site is capped at
1 GB. `.gitignore` excludes `docs/assets/**/*.pdf`; the site links to the original host for
each paper, and the extracted text is published in full. `links.tsv` and `manifest.json` are
committed, so anyone can rebuild the whole PDF corpus with `task fetch`.

If you do want the PDFs online, host them somewhere with real object storage and point
`papers.json`'s `pdf` field at that base URL — do not push them into the Pages repo.

## Sources

[tamilaruvi.in](https://www.tamilaruvi.in/p/12th-public-exam-original-question.html) (annual)
and [padasalai.net](https://www.padasalai.net) (quarterly, half-yearly), both of which mirror
the originals from the Directorate of Government Examinations,
[dge.tn.gov.in](https://dge.tn.gov.in). Papers carry the mirroring site's watermark; the
`clean` stage strips it from the text.
