---
title: Second brain architecture — tiered, Git-native, grep + SQL
type: adr
status: accepted
domain: meta
updated: 2026-10-16
tags: [second-brain, rag, duckdb, docling, mcp]
amended_by: [ADR-0002, ADR-0003]
---

# ADR-0001 — Second brain architecture

> **Amended by [ADR-0002](ADR-0002-kb-rules-as-code.md):** folder contract, rules enforced
> by hooks and lint, YAML registers, and a *deterministic* knowledge graph (an
> LLM-extracted graph stays rejected). **And by [ADR-0003](ADR-0003-agent-neutral-operation.md):**
> the same repository is operated by Claude Code and GitHub Copilot.

## Context

Project documentation is heterogeneous and heavy: specifications (Word/PDF), CSV and
Excel data, master data and reference tables, architecture diagrams as images, workshop
notes, e-mail threads, and deliverables already produced by others (designs, partial
analyses, decision logs) — often with LLM help.

Generic AI assistants degrade on such a corpus: opaque semantic chunking destroys table
relationships, large files get truncated, there is no deterministic runtime for tabular
questions, and nothing distinguishes what a source *says* from what a previous model
*inferred*. The question is which open-source building blocks give an agent grounded,
cited answers over this material at a predictable cost.

## Decision

A **repo-native, Git-versioned, tiered second brain** with three storage layers and a hard
split between what *is* (observed) and what we *intend* (design):

- **Layer 0 `source/`** — raw originals, immutable, gitignored (confidential).
- **Layer 1 `knowledge/`** — structure-aware Markdown with YAML frontmatter, produced by
  **Docling** for PDF/DOCX/PPTX and by a dedicated parser for e-mail. Ground truth for the agent.
- **Layer 2 `metadata/`** — **DuckDB** holding every tabular asset. All counting, joining
  and dependency traversal happens in SQL.
- **`artifacts/`** — the workspace the agent writes into: analyses, designs, registers, ADRs.

Retrieval is **agentic grep over the Markdown vault + SQL over DuckDB**, not a vector index.

## Adopted

| Element | Why |
|---|---|
| Docling for PDF/DOCX/PPTX | Preserves document hierarchy and renders complex tables as Markdown instead of flattening them. The single highest-value component. |
| DuckDB as tabular engine | Removes hallucination from every countable question. Zero infrastructure, in-process, reads CSV/XLSX/Parquet. |
| Observed (`knowledge/`) vs intended (`artifacts/design/`) physical separation | Addresses temporal contamination — the failure mode where current behaviour and proposed behaviour get merged into one answer. |
| Docs-as-code, Git-versioned, Markdown + frontmatter | Makes drift visible and reviewable; gives the agent a filesystem it can grep. |
| Code-as-artifact (`openpyxl`, `python-pptx`, Mermaid) | Deliverables are generated deterministically instead of being hallucinated as text. |
| Diagrams transcribed to Mermaid + prose | Makes diagram content greppable, diffable and citable. |

## Deferred (build only if a measured need appears)

| Element | Reason for deferring | Trigger to revisit |
|---|---|---|
| **Vector store + hybrid BM25** | For a corpus of hundreds of notes, a well-structured Markdown vault that a coding agent can `grep` outperforms embedding retrieval and has no chunking loss. Embeddings add an indexing pipeline, a staleness problem and a silent-failure mode. | `knowledge/` exceeds ~500 notes, or `/ask` repeatedly fails on conceptual queries no entity alias covers. |
| **MCP server** | The supported agents (Claude Code, GitHub Copilot in agent mode) have filesystem and terminal access, so they run the tools directly; an MCP layer adds no capability for them. | When an agent without terminal access must be supported. Build it as a thin, read-only, parameterised wrapper over `tools/ingest/query.py` and `tools/kb/graph.py`, not as a second implementation. |
| **Visual retrieval (ColPali-style)** | GPU-bound and heavy for a handful of diagrams. A transcription at ingestion time (the agent reads images natively) captures what is needed. | Volume of diagrams grows past what can be transcribed. |

## Rejected

| Element | Reason |
|---|---|
| **LLM-extracted knowledge graph (GraphRAG-style)** | The relations that matter are usually explicit in structured material (inventories, job lists, exports). Deriving them deterministically is exact, cheap and reproducible; LLM entity extraction adds a nondeterministic, expensive layer with unverifiable edges and entity explosion. |
| **Autonomous memory frameworks** | Too abstract to enforce hard constraints, and they hide state outside Git. Decisions must be reviewable in a pull request. |
| **Raw ingestion of Excel/PDF into the prompt** | The failure mode this design escapes. |

## Lessons that shaped the tooling

1. **Excel without network.** DuckDB's `excel` extension downloads on first use; restricted
   networks block it. `tools/ingest/build_inventory.py` reads workbooks through pandas +
   openpyxl, keeping ingestion fully offline.
2. **Model downloads behind proxies.** Docling downloads layout/table models on first run;
   TLS-intercepting proxies break that. The `tls` extra and `KB_USE_TRUSTSTORE=1` route
   Python through the OS trust store. OCR stays off by default.
3. **SQL safety.** Any tool exposed beyond Claude Code must use parameterised queries and a
   read-only connection.
4. **Docling does not recover images or embedded objects.** Measured
   (`docs/parsing-coverage.md`): tables survive, but images collapse to a placeholder and an
   object embedded in a document is **dropped silently**. `tools/ingest/extract_embedded.py`
   recovers both, and counts them, because silence is the dangerous failure mode.
5. **Parsing is a batch step.** Run once per document and cached in `knowledge/`, never on
   the agent's critical path.

## Consequences

- Every factual statement becomes citable to a file or a SQL query; hallucination on counts
  and dependencies disappears.
- The stack is small: `docling`, `duckdb`, `pandas`, `openpyxl`, `pyyaml`. No server, no
  index to keep warm, no embedding costs.
- Cost moves to **ingestion discipline**: the quality of `knowledge/` and of the DuckDB
  schema decides whether the brain works.
- Raw material stays untracked; the repository of a real project should be private.
