---
title: <object name>
type: data-object
status: draft            # draft | checked | living | superseded
origin: curated
evidence: primary-doc    # verified | primary-doc | verbal | derived-llm | assumed  (or a list)
domain: <domain from project.yaml>
system: <system that owns the object>
layer: <external-input | staging | lookup | view | report | ...>
source: source/data/<file>
duckdb_table: <table name in the structured DB>
grain: <one row per ...>
updated: YYYY-MM-DD
---

# <object name>

## Purpose

## Grain and keys
- Business key:
- Natural key(s):
- Update pattern: <full snapshot | delta | append>

## Columns
| Column | Type | Nullable | Description | Notes / domain values |
|---|---|---|---|---|

## Relationships
| Joins to | On | Cardinality | Where documented |
|---|---|---|---|

## Known data quality issues
- <rule / reject condition, with source>

## Downstream
- Feeds: `<object>` (see `tools/kb/graph.py about <object>`)
