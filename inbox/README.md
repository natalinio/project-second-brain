# Inbox

Drop new material here when its category is not obvious, then run `/ingest <file>` (or
`/ingest all`). Nothing in this folder is trusted or citable until it has been triaged
into `source/`. The folder content is gitignored.

## Where things go

| Material | Destination | Then |
|---|---|---|
| Specifications, requirements, designs, manuals (`.docx`, `.pdf`, `.pptx`, `.html`) | `source/specs/` | `parse_docs.py` → `knowledge/extracted/specs/` |
| Spreadsheets that *document* the subject (inventories, matrices, trackers) | `source/specs/` | `build_inventory.py` → DuckDB |
| Data samples, master data, reference/lookup tables (`.csv`, `.xlsx`, `.gz`) | `source/data/` | `profile_samples.py` + `build_inventory.py` → DuckDB |
| Architecture diagrams, whiteboard photos, screenshots (`.png`, `.jpg`) | `source/diagrams/` | Transcribed → `knowledge/curated/diagrams/` as Mermaid + prose |
| Meeting notes, call transcripts, workshop write-ups | `source/meeting_notes/` | `parse_docs.py` → `knowledge/extracted/meeting_notes/`, evidence `verbal` |
| **Email threads** (`.eml`, pasted `.txt`) — answers, clarifications | `source/correspondence/` | `parse_email.py` → `knowledge/extracted/correspondence/`, evidence `primary-doc` |
| Earlier deliverables (decision logs, designs, analyses — often LLM-assisted) | `source/prior_deliverables/` | `parse_docs.py` → `artifacts/_imported/` **quarantine**, evidence `derived-llm` |
| Exports produced by a system itself (DDL, object definitions, config dumps, code) | `source/system_exports/` | `parse_docs.py` → `knowledge/extracted/system_exports/`, evidence `verified` |

The dividing line for spreadsheets: `specs` is **documentation about the subject**,
`data` is **actual data to query**. Both end up in DuckDB either way.

Correspondence is its own lane rather than a kind of meeting note. A written answer from
the party that owns the subject is dated, attributable and quotable — stronger evidence
than a recollection of a conversation — and it is cited per message, not per thread,
because an answer given in June may have been superseded in September.

## Snapshot vs living version

Anything in `source/` is a **frozen snapshot** — the file exactly as received, on the date
it was produced. It is never edited, because it is the record of what a claim was based on.

The **living version you evolve** is the corresponding deliverable in `artifacts/`:

| Received deliverable | Frozen snapshot | Living version |
|---|---|---|
| Decision log | `source/prior_deliverables/` | `artifacts/registers/decisions.yaml` |
| Open points / action list | `source/prior_deliverables/` | `artifacts/registers/open_points.yaml` |
| Analysis of the current state | `source/prior_deliverables/` | `artifacts/analysis/` |
| Design, plan, estimates | `source/prior_deliverables/` | `artifacts/design/` |

Moving from one to the other is **reconciliation**, not a copy: each claim is classified
as confirmed by a primary document, contradicted, or unsupported, before anything enters
the living version. See `docs/workflow.md`.

## Triage procedure

1. Move the file to the right `source/` subfolder — never edit the original.
2. Add a row to `source/MANIFEST.md`.
3. Run the relevant ingestion (`parse_docs.py` for documents, `build_inventory.py` for tabular).
4. `/review-note` the generated note: it sets `domain`, writes the abstract and flips
   `status: extracted` → `checked`. Until then it is cited with "(extraction unchecked)".
