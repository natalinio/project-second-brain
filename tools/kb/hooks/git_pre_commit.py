"""git pre-commit: lint the staged Markdown and check the register views are current.

Install once:  uv run python tools/kb/hooks/git_pre_commit.py --install
Only staged files are linted, so unrelated work in progress never blocks a commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kbcore import MD_ROOTS, REPO  # noqa: E402

# Works on Windows (Git Bash runs hooks with sh), macOS and Linux.
HOOK = """#!/bin/sh
top="$(git rev-parse --show-toplevel)"
exec uv run --project "$top" python "$top/tools/kb/hooks/git_pre_commit.py"
"""


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8").stdout


def main() -> int:
    if "--install" in sys.argv:
        hooks = Path(git("rev-parse", "--git-path", "hooks").strip())
        hooks = hooks if hooks.is_absolute() else REPO / hooks
        hooks.mkdir(parents=True, exist_ok=True)
        target = hooks / "pre-commit"
        target.write_text(HOOK, encoding="utf-8", newline="\n")
        target.chmod(0o755)
        print(f"installed {target}")
        return 0
    staged = [f for f in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if f]
    import lint
    import registers

    rc = 0
    md = [f for f in staged if f.endswith(".md") and f.split("/", 1)[0] in MD_ROOTS]
    if md:
        rc |= lint.main(md)
    if any(f.startswith("artifacts/registers/") for f in staged):
        rc |= registers.main(["--check"])
    if rc:
        print("pre-commit: fix the errors above (or run tools/kb/refresh.py).", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
