---
name: capture
description: Record or update an open point (OP), claim (C) or decision (D) in the YAML registers of the knowledge base. Use when the user agrees to log a question, an assertion with its evidence, or a decision.
argument-hint: <op|claim|decision> <what>
disable-model-invocation: true
---
Request: $ARGUMENTS (the text typed after the command).

Edit only `artifacts/registers/{open_points,claims,decisions}.yaml`. The `.md` views are generated (editing them is blocked).

- **New item** — next free id (`uv run python tools/ingest/query.py "SELECT max(id) FROM kb.reg_open_points"`, or
  `reg_claims` / `reg_decisions`; the first item of a register is `OP-001` / `C-001` / `D-001`). Fields:
  OP: `id, title (≤140 ch), status: open, owner (TBD if unknown), text, impact, history: []`.
  Claim: `id, claim (one testable assertion), object, evidence (schema enum), source (path#Lx-Ly or SQL), contradicted_by, dependency, status: open, history: []`.
  Decision: `id (D-nnn), date, decision, rationale, ref`.
- **Change to an existing item** — do not rewrite `text`/`claim`. Set `status` / `owner` / `priority`, `updated: <today>`,
  and append to `history` one `{date: <today>, note: <one line with citation>}`.
  Resolving an OP = `status: resolved` + a decision item whose `ref` names the OP.
- Never strengthen a claim's `evidence` without citing the stronger source in `history`.

Then run `uv run python tools/kb/refresh.py` (the hook may already have regenerated the views); fix any error it reports.
Reply with one line per id touched. Nothing else.
