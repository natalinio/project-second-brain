# Operating protocol — {{PROJECT_NAME}} second brain

This file is the protocol for **every AI agent** working in this repository (Claude Code
imports it from `CLAUDE.md`; GitHub Copilot reads it directly). It is a **project knowledge
repository**, not an application: it turns heterogeneous project material
(specifications, spreadsheets, meeting notes, e-mails, diagrams, earlier deliverables)
into grounded, cited, evidence-ranked knowledge, and produces the project's deliverables
from it in a traceable, versioned way. Project context: `project.yaml`. Design rationale:
ADR-0001, ADR-0002, ADR-0003.

Rules marked **[enforced]** are checked by `tools/kb` (hooks + lint): you get an error if
you break them, so they need no further thought here. Run every tool from the repository
root with `uv run python …` — the environment is `.venv/` in this folder.

## 0. Non-negotiable rules

1. **Never answer from memory about the subject.** Every factual statement is traceable to
   a note, a register item or a SQL query. Not groundable → say "not documented" and
   propose an open point (OP).
2. **Never count, sum or join by reading a table as text.** SQL via `tools/ingest/query.py`.
3. **`source/` is immutable; the body of `knowledge/extracted/` is immutable** — only its
   frontmatter changes. Corrections and syntheses go to `knowledge/curated/`. **[enforced]**
4. **Never write a deliverable silently.** New ADRs, designs, plans: propose in chat, then
   write, then report. An `accepted` ADR is superseded, never edited. **[enforced]**
5. **What is and what we intend never in one statement.** Split and label. `knowledge/`
   and `artifacts/analysis/` describe what is (observed); `artifacts/design/` and ADRs
   what we intend.
6. **Confidential material.** `source/` content never goes to external services other
   than the AI agent approved for the project, and is never committed (gitignored). Only
   schemas, profiles and derived docs are versioned.
7. **LLM-derived work is not evidence.** `artifacts/_imported/` and DuckDB `derived_*`
   tables are hypotheses to verify, never cited as fact. **[enforced: folder evidence]**
8. **Never strengthen evidence without a citation.** A claim or note moves to a stronger
   level only with the stronger source recorded.

## 1. Repository map

| Path | Contract |
|---|---|
| `inbox/` | Drop zone. Untrusted until triaged (`/ingest`). |
| `source/` | Raw originals, immutable, gitignored. `MANIFEST.md` is the versioned register. |
| `knowledge/extracted/` | Parser output of `source/` (Docling, e-mail). Body immutable. `status: extracted → checked` (`/review-note`). |
| `knowledge/curated/` | Syntheses we write: data dictionary, diagrams (Mermaid), summaries of material that has no file. |
| `metadata/inventory.duckdb` | Every tabular asset. Rebuilt by `tools/ingest/build_inventory.py`. |
| `metadata/kb.duckdb` | The brain's index: `catalog`, `sections`, `reg_*`, `nodes`, `edges`. Rebuilt by `tools/kb/refresh.py`. Attached as schema `kb` in `query.py`. |
| `artifacts/analysis/` | Our analysis of the current state: reconciliations, contradictions, lineage. |
| `artifacts/design/` | What we intend: designs, mappings, plans. |
| `artifacts/registers/` | `open_points`, `claims`, `decisions`: **edit the `.yaml`**, the `.md` views are generated. **[enforced]** |
| `artifacts/adr/` | Architecture Decision Records. |
| `artifacts/_imported/` | Quarantined prior deliverables, `derived-llm`. |
| `tools/` | `ingest/` parsers and SQL, `kb/` rules-as-code and hooks. |
| `.claude/skills/` | The commands below, shared by Claude Code and GitHub Copilot. |

Folder contract, vocabularies, registers and thresholds: `tools/kb/schema.yaml` (single
source). Graph sources: `tools/kb/graph_sources.yaml`; concepts: `tools/kb/entities.yaml`.

## 2. Commands (the normal way to work)

Slash commands in both agents (Claude Code: type `/`; Copilot Chat in agent mode: type `/`).

| Command | Use it to |
|---|---|
| `/ask <question>` | answer, grounded and cited |
| `/ingest <file>` | bring new material in and see what it changes |
| `/capture <op\|claim\|decision> …` | record or update a register item |
| `/impact <id\|object>` | see what depends on something before changing it |
| `/review-note <path>` | check an extraction and write its abstract |
| `/kb-status` | KB health and next actions |
| `/init-brain` | one-off set-up after creating the repository |

After any change to `knowledge/` or the registers: `uv run python tools/kb/refresh.py`.

## 3. Grounding order — cheapest first, stop when grounded

1. `uv run python tools/kb/graph.py about <object|concept>` — relations, register items
   and the **note sections** (path + line range) that mention it.
2. SQL: `uv run python tools/ingest/query.py "…"` — structured tables, or `kb.*`
   (registers, catalog, sections).
3. Read only the line ranges from steps 1–2. Never read a whole note above 40 KB.
4. Text search, only when 1–3 return nothing.

`artifacts/` is what *we* produced — never evidence about the subject. Two sources
disagree → report both and propose an OP; do not pick one.

## 4. Evidence and citation

| Level | Stated as fact? |
|---|---|
| `verified` — system export, DDL, source code, system catalog | Yes |
| `primary-doc` — document by whoever owns the subject | Yes, with the citation |
| `verbal` — meeting, workshop, chat | Yes, attributed and dated |
| `derived-llm` — produced by an LLM | **No** — hypothesis |
| `assumed` — our inference | **No** — labelled wherever used |

- Cite `path#Lstart-Lend` (or the SQL). A note with `status: extracted` is cited with
  "(extraction unchecked)".
- Every observed assertion a design depends on is a claim `C-nnn` in the claims register;
  the deliverable cites the id. No ad-hoc evidence legends in deliverables.
- A design resting on anything weaker than `primary-doc` states the assumption in the
  deliverable itself, with its claim id and what would verify it.

## 5. Output economy (tokens are a budget)

- Answer first, evidence after; ≤ 15 lines unless asked for more. No preambles, no recaps
  of what you read, no restating the question.
- Prefer one graph/SQL call over several searches; read line ranges, not files.
- Do not re-read a file you just wrote; the post-write hook already linted it and is
  silent when it is clean.
- For broad multi-file analysis, split the work into read-only sub-tasks and consolidate.

## 6. Writing

- Frontmatter per `tools/kb/schema.yaml`: `title, type, status, evidence, updated`
  (+ `origin`, `perspective`, `abstract` above 40 KB). Context goes in `status_note` /
  `evidence_note`, never inside an enum field. **[enforced]**
- Atomic notes: one object, one rule set, one decision per file.
- Notes and deliverables in the language set in `project.yaml`; quote the original
  verbatim when nuance matters.
- Deliverables are generated as code (`openpyxl`, `python-pptx`, Mermaid), kept under `tools/`.

## 7. Definition of done

- [ ] Every claim grounded and cited (`path#L…` or SQL shown)
- [ ] Observed and intended kept separate
- [ ] Unknowns proposed as OPs, assumptions registered as claims
- [ ] `uv run python tools/kb/refresh.py` clean (0 lint errors)
- [ ] Decision recorded (`/capture decision`, or an ADR if it constrains future work)
