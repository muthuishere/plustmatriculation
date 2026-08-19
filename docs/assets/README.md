# TN +2 (HSC 2nd Year) Question Papers — Science

Tamil Nadu Class 12 papers for **Physics, Chemistry, Maths, Biology, Botany, Zoology**.
866 PDFs (1644 MB), 866 markdown conversions (116 of them recovered by OCR).

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

| Subject | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | na | total |
|---|---|---|---|---|---|---|---|---|---|---|
| Physics | — | 1 | 1 | 1 | 1 | 1 | 1 | 1 | — | 7 |
| Chemistry | — | 2 | 1 | 1 | 1 | 1 | 1 | 1 | — | 8 |
| Maths | — | 2 | 1 | 1 | 1 | 1 | 1 | 1 | — | 8 |
| Biology | — | 2 | 1 | 1 | 1 | 1 | 1 | 1 | — | 8 |
| Botany | — | 2 | 1 | 1 | 1 | 1 | 1 | 1 | — | 8 |
| Zoology | — | 2 | 1 | 1 | 1 | 1 | 1 | 1 | — | 8 |

### Quarterly

| Subject | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | na | total |
|---|---|---|---|---|---|---|---|---|---|---|
| Physics | — | — | — | 13 +2ak | 7 +4ak | 21 +9ak | 27 +10ak | 0 +1ak | 1 | 95 |
| Chemistry | 2 +3ak | — | — | 5 | 9 +3ak | 14 +4ak | 29 +17ak | 0 +1ak | — | 87 |
| Maths | 2 +2ak | — | — | 10 +1ak | 12 +3ak | 25 +9ak | 44 +21ak | 0 +2ak | 1 | 132 |
| Biology | 1 +1ak | — | — | 4 | 7 +2ak | 13 +3ak | 29 +7ak | 0 +1ak | — | 68 |
| Botany | — | — | — | 1 | 0 +2ak | 1 +1ak | 10 +2ak | 0 +1ak | — | 18 |
| Zoology | — | — | — | 2 +1ak | 3 +4ak | 4 +4ak | 9 +3ak | 0 +1ak | — | 31 |

### Half-yearly

| Subject | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | na | total |
|---|---|---|---|---|---|---|---|---|---|---|
| Physics | 1 +2ak | 1 | — | 9 | 15 +2ak | 15 +10ak | 13 +9ak | — | — | 77 |
| Chemistry | 0 +5ak | — | — | 11 +4ak | 12 +1ak | 26 +6ak | 32 +18ak | — | — | 115 |
| Maths | 1 +3ak | 1 | — | 15 +4ak | 13 +2ak | 23 +10ak | 28 +7ak | — | — | 107 |
| Biology | 1 | 1 | — | 6 | 4 +1ak | 11 +2ak | 14 +5ak | — | — | 45 |
| Botany | — | — | — | 1 | 1 | — | 2 +8ak | — | — | 12 |
| Zoology | 1 | — | — | 5 +5ak | 3 +1ak | 2 +3ak | 5 +7ak | — | — | 32 |

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
