---
title: Customising the second brain for a project
type: guide
status: living
updated: 2026-10-16
---

# Customising the second brain

Everything project-specific is configuration. The Python under `tools/` should not need
to change for a new project; if it does, consider whether the change is generic and
belongs upstream.

| You want to | Edit | Then |
|---|---|---|
| Name the project, list domains and owners | `project.yaml` | `/init-brain` (once) |
| Make the graph know your objects and their relations | `tools/kb/graph_sources.yaml` | `refresh.py` |
| Make prose mentions of systems, parties, concepts resolvable | `tools/kb/entities.yaml` | `refresh.py` |
| List the key tables in the index | `tools/kb/index_key_tables.yaml` | `refresh.py` |
| Change evidence levels, statuses, required fields | `tools/kb/schema.yaml` | an ADR explaining why |
| Add a source lane (e.g. `source/tickets/`) | `tools/ingest/parse_docs.py` `ROUTES`, `inbox/README.md`, `schema.yaml` `catalog_groups` | `refresh.py` |
| Add a register field | the YAML items (free fields are kept); `tools/kb/registers.py` to show it in the view | `refresh.py` |
| Protect another folder | `schema.yaml` `protected` | restart Claude Code |
| Tune what counts as an identifier | `schema.yaml` `identifier` | `refresh.py` |

## Graph sources

`graph_sources.yaml` turns any CSV or SQL result into graph nodes and edges. A typical
first source is an inventory spreadsheet loaded by `build_inventory.py`:

```yaml
sources:
  - name: interface inventory
    type: sql
    query: SELECT interface_id, source_system, target_system FROM interfaces_inventory
    evidence: primary-doc
    nodes:
      - {column: interface_id,  kind: interface}
      - {column: source_system, kind: system}
      - {column: target_system, kind: system}
    edges:
      - {src: source_system, dst: interface_id,  rel: feeds}
      - {src: interface_id,  dst: target_system, rel: feeds}
```

- `feeds` edges drive `graph.py about` (upstream/downstream) and `graph.py path`.
- `reads` / `writes` from a `job`-like node show as "Touched by".
- Any other verb (`calls`, `owns`, `hosts`...) is listed under "Relations".
- `evidence` is the evidence level of the source: an inventory someone maintains by hand
  is `primary-doc`; a catalogue exported from the system itself is `verified`; a table
  recovered from an inherited LLM-made report is `derived-llm`, and `graph.py` flags
  lineage that rests only on such edges.

Identifiers are matched verbatim in every note section, so `graph.py about <ID>` lists the
exact line ranges to read. Short or ordinary words are never matched (see `identifier` in
`schema.yaml`); put such names in `entities.yaml` with explicit aliases instead.

## A note that defines an object

A curated note can declare `defines: <ID>` (or a list) in its frontmatter. The graph then
shows it under "Defined in" for that object — the first place to read.

## Analyzers

Project-specific analysis scripts (e.g. parsing exported object definitions into a
dependency table) belong in `tools/analyze/` of your fork. Pattern: read from `source/` or
`knowledge/extracted/`, write a DuckDB table into the structured DB and, if useful, a
generated report under `metadata/`; then declare the table in `graph_sources.yaml`.

## Deliverable builders

Scripts that generate deliverables (Excel matrices, slide decks, HTML explorers) go in
`tools/build/`. Generate from the registers and the DuckDB tables, never from free text,
so a regenerated deliverable reflects the current evidence.

## Commands and models

The commands are Agent Skills in `.claude/skills/<name>/SKILL.md`, read by both Claude
Code and GitHub Copilot. Edit a skill once and both agents use the new version; add a
skill folder to add a command. They run on the model selected in your session. Mechanical
skills (`capture`, `impact`, `kb-status`) work well on a small, cheap model.
