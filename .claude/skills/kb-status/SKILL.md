---
name: kb-status
description: Health of the knowledge base in one table plus the next three actions. Use to see what needs attention (lint errors, unowned open points, unchecked extractions, files waiting in inbox/).
---
1. `uv run python tools/kb/refresh.py`
2. Print the `AUTO:status` block of `knowledge/index.md` and the lint summary line, as they are.
3. At most 3 bullets of next actions, by value: lint errors to fix; open OPs with owner `TBD`
   (`SELECT id, title FROM kb.reg_open_points WHERE owner = 'TBD' AND status = 'open'`); large unchecked
   extractions (`SELECT path, chars FROM kb.catalog WHERE status = 'extracted' ORDER BY chars DESC LIMIT 3`);
   files still waiting in `inbox/`.
No other commentary.
