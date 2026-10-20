"""Rebuild the whole brain index in one go, terse output. Run after any KB change.

    python tools/kb/refresh.py           # registers -> catalog/index/README -> graph -> lint
    python tools/kb/refresh.py --check   # read-only: stale views or lint errors -> exit 1

Each step prints one line; only errors are listed in full.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import build_catalog  # noqa: E402
import build_graph  # noqa: E402
import lint  # noqa: E402
import registers  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        rc = registers.main(["--check"])
        return rc or lint.main([])
    rc = registers.main([])
    if rc:
        return rc
    build_catalog.main([])
    build_graph.main([])
    return lint.main([])


if __name__ == "__main__":
    raise SystemExit(main())
