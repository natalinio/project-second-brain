---
name: impact
description: Show what depends on a claim, open point, decision, ADR, note or object in the knowledge base. Use before changing, contradicting or deleting something.
argument-hint: <C-nnn | OP-nnn | D-nnn | ADR-nnnn | object | note path>
---
Target: $ARGUMENTS (the text typed after the command).

Run `uv run python tools/kb/graph.py impact <target>` (for an object also `graph.py about <target> --limit 8`).
Report the dependent deliverables and register items as a short list, and say which need review if it changes.
Do not open the files unless asked.
