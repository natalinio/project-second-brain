"""PostToolUse hook (Claude Code and GitHub Copilot): lint what was just written.

  * a .md under knowledge/, artifacts/ or docs/  -> lint that file
  * a register YAML under artifacts/registers/   -> regenerate the views, then validate
Silent on success, so a clean write costs the agent no tokens. Errors are handed back to
the agent (see agent_io.feedback).
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_io import feedback, read_call  # noqa: E402
from kbcore import MD_ROOTS, REPO  # noqa: E402
from pre_tool import relpath  # noqa: E402


def main() -> int:
    call = read_call()
    if call is None or call.kind not in ("write", "patch"):
        return 0
    errors = []
    for p in call.paths:
        r = relpath(p)
        if r is None:
            continue
        buf = io.StringIO()
        if r.startswith("artifacts/registers/") and r.endswith(".yaml"):
            import registers

            with redirect_stdout(buf):
                code = registers.main(["--quiet"])
        elif r.endswith(".md") and r.split("/", 1)[0] in MD_ROOTS and (REPO / r).exists():
            import lint

            with redirect_stdout(buf):
                code = lint.main([r])
        else:
            continue
        if code:
            errors.append(buf.getvalue().strip())
    return feedback(call, "\n".join(errors)) if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
