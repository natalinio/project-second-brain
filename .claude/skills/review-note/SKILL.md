---
name: review-note
description: Check the fidelity of one extracted note (structure, tables, images — not its content), write its abstract and mark it checked. Use on notes in knowledge/extracted/ with status extracted.
argument-hint: <path of a knowledge/extracted note>
---
Note: $ARGUMENTS (the text typed after the command).

Sample, don't read the whole note:
1. **Structure** — `uv run python tools/ingest/query.py "SELECT heading, line_start, line_end FROM kb.sections WHERE path = '<path>' ORDER BY line_start"`.
   Headings plausible and in order? A single section spanning > 1,000 lines = lost hierarchy (note it).
2. **Tables** — read 2 table-bearing sections (by line range): columns aligned, nothing flattened into prose.
3. **Images** — count `NOT YET DESCRIBED` / `NOT EXTRACTED` placeholders. List the count; do not describe them now.
4. **Frontmatter** — `domain` (not TODO; one of the `domains` in `project.yaml` when listed); `evidence` right for
   the type; `abstract` of 3–5 lines (what it is, what it is authoritative for, main sections with line ranges)
   when the note is above the abstract threshold (40 KB by default).

Then edit the **frontmatter only** (the body is immutable, hook-enforced): `status: checked`,
`status_note: "checked <today>: <issues or ok>"`, `domain`, `abstract`. If the extraction is defective
(lost tables, missing pages), keep `status: extracted` and propose an OP instead.
Reply in ≤ 5 lines.
