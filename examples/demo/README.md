# Demo project — order platform (fictional)

A tiny, entirely fictional project used by the quickstart, the tests and CI. It shows every
layer of the second brain working end to end without needing Docling or any real material.

```bash
uv run python tools/kb/bootstrap.py --demo --no-hook   # in a scratch copy or a fresh fork
uv run python tools/kb/graph.py about ORDERS_DAILY
uv run python tools/ingest/query.py "SELECT id, status, title FROM kb.reg_open_points"
```

`bootstrap.py --demo` copies these files over the skeleton (same relative paths), parses
the e-mail with `parse_email.py`, loads the CSV with `build_inventory.py` and refreshes the
index. The two notes under `knowledge/extracted/` stand in for Docling output, so the demo
runs on the core dependencies only.

The story: A team is reviewing how orders flow from its order service into the reporting
warehouse. A specification, a kickoff workshop and an e-mail disagree on how long
cancelled orders are retained — the registers show how that conflict is captured as a
claim, an open point and, eventually, a decision.
