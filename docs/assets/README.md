# TN +2 (HSC 2nd Year) Public Exam Question Papers — Science

Original Directorate of Government Examinations (DGE), Tamil Nadu question papers.
Every paper is printed **bilingually — "Tamil & English Version"** — so these serve
English-medium students directly. Files are scans (image PDFs, no text layer);
source watermark: tamilaruvi.in.

Naming: `12th-<subject>-<year>-<exam-month>.pdf`

| Subject | 2020 Apr | 2020 Sep | 2021 May | 2022 May | 2023 Apr | 2024 Mar | 2025 Mar | 2026 Mar |
|---|---|---|---|---|---|---|---|---|
| Physics   | —  | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Chemistry | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Maths     | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Botany    | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Zoology   | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Biology   | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

47 papers, ~52 MB.

Notes:
- **Biology** is the combined paper (Bio-group / vocational stream). The academic
  Bio-Maths & Pure-Science streams write **Botany** and **Zoology** as separate papers —
  all three are included.
- **Physics April 2020 is absent**: that paper was among the March-2020 sittings
  disrupted by the COVID lockdown; the September 2020 supplementary is the 2020 Physics paper.
- 2021 papers are the "Type A" variants (the only set published that year).

Source: [tamilaruvi.in — 12th Public Exam Original Question Papers](https://www.tamilaruvi.in/p/12th-public-exam-original-question.html),
which mirrors the DGE originals. Official portal: [dge.tn.gov.in](https://dge.tn.gov.in).

## Markdown conversions

Both directories mirror the PDF filenames one-for-one (47 files each). **The PDFs are untouched
and remain the source of truth.**

| Directory | What it is | Size |
|---|---|---|
| `markdown/` | Raw [Microsoft MarkItDown](https://github.com/microsoft/markitdown) output — full fidelity, nothing removed | 8.9 MB |
| `markdown-english/` | Same text, de-spammed: watermark runs stripped, Tamil column dropped, English questions only | 364 KB |

### Why two sets

These PDFs are **not** pure scans — they carry a real text layer, so no OCR was needed. But two
things make the raw output rough:

1. **The Tamil is mojibake.** DGE typesets Tamil in a legacy 8-bit font (Bamini-family), so it
   extracts as Latin garbage (`C¯Ø¤¯À` = `இயற்பியல்`). Unfixable by re-extraction — it needs a
   glyph-level transcoding pass. The **English extracts cleanly**, including maths symbols
   (α, β, Σ, √, superscripts).
2. **The watermark dominates.** `www.tamilaruvi.in` / `https://t.me/tamilaruviweb` repeats
   hundreds of times per page — that alone is ~97% of the raw byte count.

`markdown-english/` fixes both, which is why it is 25× smaller. Use it for search, RAG, or
question-bank extraction; use `markdown/` if you ever want to recover the Tamil layer.

### Known artifact

Reading order follows the PDF's two-column layout, so an MCQ's options sometimes appear **before**
its question stem, and Tamil-side option labels `(A)(B)(C)(D)` survive alongside the English
`(a)(b)(c)(d)` when the options are formulae. Fine for search; needs a reflow pass before
rendering as a clean question bank.
