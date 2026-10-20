---
title: Working method
type: process
status: living
updated: 2026-10-16
---

# Working method

The second brain supports any project that has to reason over a body of material it did
not write: a system review, a migration, a due diligence, an audit, a product discovery.
The method is the same: **build an evidence base first, reconcile what others already
concluded, design on an explicit evidence floor, and verify when authoritative material
arrives.**

The most authoritative material (system exports, source code, signed-off documents) is
often *not* available at the start. That does not block the work — it changes its order.
Build everything that does not depend on it, and structure the work so that its arrival
becomes a *verification pass* rather than a restart.

---

## Phase A — Build the evidence base from what exists

**Input:** specifications, spreadsheets, data samples, reference tables, diagrams,
meeting notes, e-mails.

1. **Triage.** Drop files in `inbox/`, `/ingest` them: each is sorted into a `source/`
   lane and registered in `source/MANIFEST.md`. Earlier deliverables go to
   `source/prior_deliverables/` — they are handled separately in Phase B.
2. **Recover embedded content.** `extract_embedded.py` → images and objects embedded
   inside Office files land in `source/_extracted/`, counted in
   `metadata/extraction_report.md`. Must run *before* the next two steps, or workbooks
   embedded inside other files never reach DuckDB. See `docs/parsing-coverage.md`.
3. **Parse.** `parse_docs.py` / `parse_email.py` → `knowledge/extracted/` as
   `status: extracted`. The note is citable at its evidence level, marked "(extraction
   unchecked)". `/review-note` checks the extraction and sets `checked`. The body is never
   edited: rules lifted out of it, and any correction, go into a `knowledge/curated/` note
   that cites the extracted lines.
4. **Load.** `build_inventory.py` → every CSV and every spreadsheet tab becomes a DuckDB
   table. From here, counting and joining is SQL.
5. **Data dictionary.** One note per data object in `knowledge/curated/data_dictionary/`
   (template: `docs/templates/data-dictionary-template.md`): columns, types, grain, keys,
   update pattern, known quality issues.
6. **Transcribe diagrams.** `grep -rn "NOT YET DESCRIBED" knowledge/` lists every extracted
   image still without a description. Each is transcribed into
   `knowledge/curated/diagrams/` as Mermaid plus prose — greppable, diffable, citable.
7. **Declare structure.** Point `tools/kb/graph_sources.yaml` at the inventories that list
   objects and their relations (jobs, tables, services, interfaces); add recurring systems,
   parties and concepts to `tools/kb/entities.yaml`. The graph now answers "what touches X".
8. **Claims register.** Every atomic assertion about the current state that a design will
   depend on becomes a claim (`/capture claim`), tagged with its evidence level. This
   converts missing authoritative material from a hidden risk into a scoped task.

**Exit criterion:** every reviewed document has produced claims, and the coverage table in
the claims register shows how much rests on `primary-doc` versus `assumed`.

---

## Phase B — Reconcile inherited deliverables

Analyses and designs produced before the brain existed — often with an LLM, from the same
documents — are valuable but **second-hand**. They are imported as `evidence: derived-llm`
into `artifacts/_imported/` and reconciled, never copied into `knowledge/`.

For each claim they contain, exactly one outcome:

| Outcome | Action |
|---|---|
| Confirmed by a primary document | Register the claim at `primary-doc`, cite the document |
| Contradicted by a primary document | Record the contradiction; anything built on it is revisited (`/impact`) |
| Neither confirmed nor contradicted | Stays `derived-llm`, unusable as fact, queued for verification |

The third bucket is the interesting one. Its size is the honest measure of how much of the
current understanding is actually unsupported — and it is normally larger than anyone
expects.

**Exit criterion:** every claim in the inherited deliverables is classified. No orphans.

---

## Phase C — Design on an explicit evidence floor

Designs, mappings and plans in `artifacts/design/` are produced from the registers, not
from free recall. Every design decision that rests on a claim weaker than `primary-doc`
carries the assumption visibly, in the deliverable itself:

> The nightly load drops orders with an unknown customer id.
> **Assumption (claim C-nnn, `derived-llm`):** the current job rejects rather than
> defaults these rows. Source: inherited analysis, not confirmed by any specification.
> Verify against the job definition when the system export arrives.

This keeps the plan usable today while making its soft spots impossible to lose.

---

## Phase D — Verification pass (when authoritative material arrives)

Not a rewrite. A pass over the register:

1. Put the exports (DDL, object definitions, job definitions, code) into
   `source/system_exports/`; they parse at evidence `verified`.
2. For each claim with a design dependency, in risk order: confirm, contradict, or mark
   still-unknown (`/capture`, with the citation in `history`).
3. For each contradiction, run `/impact` and open an ADR amendment for the design that
   relied on it.
4. The claims coverage table recomputes itself on the next refresh.

The value of Phases A–C is precisely that this pass is mechanical.

---

## Sequencing heuristic

Work domain by domain, not layer by layer, and start with **shared master data and
reference tables**. Every other flow joins to them, their samples are usually in hand
early, and they are the cheapest place to discover that the documentation and the data
disagree.
