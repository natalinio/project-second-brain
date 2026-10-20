---
name: ingest
description: Bring new material from inbox/ into the knowledge base — triage into source/, parse, refresh — and report what it confirms, contradicts or extends. Use when files were dropped into inbox/.
argument-hint: <file in inbox/ | all>
disable-model-invocation: true
---
Input: $ARGUMENTS (the text typed after the command).

1. **Triage.** Classify each file with the table in `inbox/README.md`; move it to that `source/` subfolder
   (never edit the original); add a row to `source/MANIFEST.md` in that section's format.
2. **Parse.** Office/PDF documents → `uv run python tools/ingest/extract_embedded.py --only "<name>"`, then
   `uv run python tools/ingest/parse_docs.py --only "<name>"`; `.eml` → `uv run python tools/ingest/parse_email.py`;
   spreadsheets/CSV → `uv run python tools/ingest/build_inventory.py`. Images → transcribe into
   `knowledge/curated/diagrams/` (Mermaid + prose, `origin: curated`). Content that has no file (a chat, a call)
   → a curated note in `knowledge/curated/<kind>/`, `evidence: verbal`, attributed and dated.
3. **Refresh.** `uv run python tools/kb/refresh.py`; fix lint errors in what you wrote.
4. **Delta, bounded.** Run `graph.py about` on the 3–5 main objects of the new material and keep only the sections
   of the new note. Report at most 10 bullets: each new fact → confirms / contradicts / extends an existing claim,
   OP or decision (with ids), cited `path#Lx-Ly`. Do not summarise the whole document.
5. **Propose** register changes (close/narrow OP, new claim, new OP, decision, contradiction) as a short list.
   Apply them with `/capture` only after the user agrees. New recurring names → propose aliases for
   `tools/kb/entities.yaml`.

Never edit the body of a `knowledge/extracted/` note (hook-enforced): corrections and syntheses go to `knowledge/curated/`.
