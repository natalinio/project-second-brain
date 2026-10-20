---
title: <object or topic>
type: <spec | data-object | diagram | meeting-note | summary | ...>
status: draft            # curated: draft | checked | living | superseded  (tools/kb/schema.yaml)
origin: curated          # knowledge/curated/ only — extracted notes come from the parsers
evidence: primary-doc    # verified | primary-doc | verbal | derived-llm | assumed  (or a list)
evidence_note:           # optional: why, when composite or unusual
domain: <domain from project.yaml>
source: source/<relative path to the original>
defines:                 # optional: the object id this note is the definition of (graph edge)
updated: YYYY-MM-DD
tags: []
---

# <title>

> Observed facts only. Designs and decisions belong in `artifacts/`.

## Summary

## Details
<Curated content. Keep tables as Markdown tables.>

## Rules
- Rule — source: <path#Lx-Ly or section / page>

## Open questions
- <OP-nnn in artifacts/registers/open_points.yaml>

## Related
- `knowledge/curated/<folder>/<other-note>.md` — cite paths (checked by the lint), not wikilinks
