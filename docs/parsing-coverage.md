---
title: Parsing coverage — what survives extraction and what does not
type: process
status: living
updated: 2026-10-16
---

# Parsing coverage

Measured on purpose-built fixtures (a `.docx` with a table and an image, an `.xlsx`
with a chart, an image and an embedded workbook, a `.pptx` with a table and an image,
and a PDF containing an image), not assumed from documentation.

The reason this page exists: **the failure mode of a document pipeline is silence.**
Content that is dropped does not raise an error — it simply is not there, and nobody
notices until a decision has been built on its absence.

## Verified results

| Content | Docling alone | With this pipeline | Notes |
|---|---|---|---|
| Headings, paragraphs, hierarchy | ✅ | ✅ | Document tree preserved |
| Tables in `.docx` | ✅ | ✅ | Rendered as Markdown tables, intact |
| Tables in `.pptx` | ✅ | ✅ | |
| Tables in `.pdf` | ✅ | ✅ | Table-structure model; needs its download to have succeeded once |
| Excel sheet data | ✅ | ✅ | Also loaded into DuckDB, which is the path to actually use |
| **Excel chart cached values** | ✅ | ✅ | The plotted series comes through as a table |
| **Images (all formats)** | ❌ `<!-- image -->` | ✅ extracted | Placeholder keeps the position, loses the content. We save the bitmap and link it |
| **Embedded objects** (a workbook inside a workbook, an OLE object) | ❌ **silently dropped** | ✅ recovered | Stored under `xl/embeddings/` in the file's zip; Docling never looks there |
| Legacy `.doc` / `.xls` / `.ppt` | ❌ | ⚠️ partial | Unwrapped from OLE where possible (`ole` extra), but convert to OOXML for reliable parsing |
| Scanned pages (OCR) | ⚠️ | ⚠️ opt-in | `parse_docs.py --ocr`; downloads an OCR model on first use |
| E-mail (`.eml`, pasted `.txt`) | — | ✅ | `parse_email.py`: one note per thread, one section per message |
| Data embedded in HTML reports (JS literals) | ❌ near-empty page | ✅ | `extract_html_data.py` → DuckDB `derived_*` tables |

## The two gaps we fill, and how

### Images

`tools/ingest/parse_docs.py` saves every picture to `source/_extracted/<doc>/media/`
and rewrites the placeholder in the note to:

```
<!-- image: source/_extracted/<doc>/media/pic_000.png — NOT YET DESCRIBED -->
```

Bitmaps stay **out of Git** (they derive from confidential documents; `source/` is
gitignored) while their position in the document is preserved and every undescribed image
is greppable:

```bash
grep -rn "NOT YET DESCRIBED" knowledge/ artifacts/
```

A vision-capable agent then reads each image and transcribes it into
`knowledge/curated/diagrams/` as **Mermaid plus prose**, citing the image path. The
placeholder in the extracted note stays as it is (extracted bodies are immutable); the
curated note is what the graph links to the image's objects. A transcribed diagram is
greppable, diffable and citable; a PNG is none of those things. This is deliberately a
human-reviewed step — a misread arrow in an architecture diagram is exactly the kind of
error that propagates silently.

### Embedded objects

`tools/ingest/extract_embedded.py` opens each Office file as the zip it actually is and
pulls out `*/media/*` and `*/embeddings/*`, unwraps OLE containers (`Package`,
`Ole10Native`, PDF `CONTENTS`, legacy `Workbook`/`WordDocument` streams), and recurses
into any OOXML file it recovers. Recovered workbooks are loaded into DuckDB under an
`embedded_` prefix, so provenance is visible in every query that touches them.

`metadata/extraction_report.md` lists everything found — the point is that recovered
content is **counted**, so its absence would be noticeable.

## Order of operations

```bash
uv run python tools/ingest/extract_embedded.py    # 1. recover images + embedded objects
uv run python tools/ingest/profile_samples.py     # 2. physical format of data samples
uv run python tools/ingest/build_inventory.py     # 3. all tabular data -> DuckDB
uv run python tools/ingest/extract_html_data.py   # 4. data inside HTML reports -> DuckDB
uv run python tools/ingest/parse_docs.py          # 5. documents -> Markdown notes
uv run python tools/ingest/parse_email.py         # 6. e-mail threads -> Markdown notes
uv run python tools/kb/refresh.py                 # 7. registers, catalog, graph, lint
grep -rn "NOT YET DESCRIBED" knowledge/           # 8. transcribe diagrams
```

Step 1 must precede step 3, or workbooks embedded inside other files will not be in
DuckDB; step 4 appends to the database step 3 built. `/ingest` runs the relevant steps
for each new file.

## Known limits

- **Merged cells and stacked tables in Excel.** A tab holding several tables one under
  another, or with merged header cells, is loaded as one messy table or skipped with a
  warning. It is flagged, never silently reshaped — splitting it is an ingestion
  decision, made once, not a query-time guess.
- **A sheet containing only an image** reads as empty and is skipped with a warning; its
  image is still recovered by step 1.
- **Legacy binary formats.** Re-save as `.docx`/`.xlsx` where possible.
- **Long batches.** Docling can crash on long runs of large PDFs; use
  `parse_docs.py --isolate` (one subprocess per document).
- **Placeholder ordering.** Images are matched to placeholders by document reading order.
  Worth a spot-check on the first real document with many images.
