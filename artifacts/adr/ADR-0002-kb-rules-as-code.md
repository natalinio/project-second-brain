---
title: KB rules as code — schema, hooks, lint, registers and a deterministic graph
type: adr
status: accepted
domain: meta
updated: 2026-10-16
tags: [second-brain, lint, hooks, registers, knowledge-graph, duckdb]
---

# ADR-0002 — KB rules as code

## Context

ADR-0001 set up the tiered vault with its rules written in prose (the protocol in
`AGENTS.md`). In real use, after a few weeks such rules stop governing the content:

- notes declared "uncitable until reviewed" get cited anyway, because the review gate
  cannot be operated at the pace material arrives;
- the claims register stalls while deliverables grow their own ad-hoc evidence legends;
- `status` and `evidence` fields fill with free text; parser defaults (e.g. a meeting note
  marked `primary-doc`) go uncorrected;
- parser output and authored syntheses mix in one folder, current-state analysis and
  design in another;
- registers kept as Markdown tables turn into narrative, rows lose owners, indexes go stale;
- large notes have no map, so every question costs whole-file reads.

The common cause: rules that only an agent's attention enforces drift, and enforcing them
by attention is also what consumes the token budget.

## Decision

Everything deterministic moves out of the prompt into `tools/kb/`:

1. **One schema** (`tools/kb/schema.yaml`): evidence and status vocabularies, folder
   contract, protected folders, required fields, type→evidence rules, register id formats
   and statuses, abstract threshold. Context goes to `status_note` / `evidence_note`.
2. **Layout**: `knowledge/extracted/` (parser output, body immutable) vs
   `knowledge/curated/` (syntheses); `artifacts/analysis/` (observed) vs
   `artifacts/design/` (intended); `artifacts/registers/`, `artifacts/adr/`,
   `artifacts/_imported/` (quarantine).
3. **Citability** replaces "draft is uncitable": a note is citable at its evidence level; an
   unchecked extraction is cited with "(extraction unchecked)". `/review-note` checks
   fidelity and sets `checked`.
4. **Enforcement**: agent hooks (Claude Code, GitHub Copilot — ADR-0003) block writes to `source/`, body edits to extracted
   notes and accepted ADRs, and hand edits to generated views; a lint
   (`tools/kb/lint.py`) validates frontmatter, links, cited paths and ids after every write
   and in a git pre-commit hook.
5. **Registers** are YAML (`artifacts/registers/*.yaml`) with generated Markdown views and
   DuckDB tables (`kb.reg_*`); updates append to `history` instead of rewriting text.
6. **Catalog and section map** (`kb.catalog`, `kb.sections`) generate the index and let an
   agent read line ranges instead of files.
7. **Knowledge graph — deterministic.** `kb.nodes` / `kb.edges` built from declared
   structured sources (`tools/kb/graph_sources.yaml`), a concept dictionary
   (`tools/kb/entities.yaml`), register items and exact identifier/alias matches per
   innermost note section. Edges carry the evidence of their source.
   `tools/kb/graph.py about | impact | path` is the first grounding step.
8. **Commands** (skills in `.claude/skills/`) package the procedures with fixed output budgets, the
   mechanical ones on smaller models.

## Relation to ADR-0001

- ADR-0001 rejected an *LLM-extracted* knowledge graph; that stays rejected. This graph has
  no LLM in it: it materialises references that already exist in structured form.
- The vector store stays deferred, with a measurable trigger: `/ask` repeatedly failing on
  conceptual queries that no entity or alias in `tools/kb/entities.yaml` covers.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the prose rules, re-review by hand | That is the state that drifts; it also spends tokens on every turn |
| Embedding retrieval for search | Exact identifiers dominate the questions; adds staleness and silent misses |
| LLM-built graph (GraphRAG) | Nondeterministic, expensive, unverifiable edges — the opposite of the evidence model |
| Move the KB to a database application | Loses Git review and diffable Markdown |

## Consequences

- Breaking a rule produces an error at write time; the agent no longer re-reads the
  protocol to stay compliant.
- One question about an object costs one graph call plus a few line-range reads.
- `tools/kb/refresh.py` must run after content changes (the commands do it).
- The graph is only as good as its sources and its entity dictionary: missing aliases are
  added to `entities.yaml` as they are found.
