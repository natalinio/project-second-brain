"""Apply frontmatter fields to many notes from one YAML file (batch /review-note results).

    python tools/kb/apply_frontmatter.py batch.yaml [--dry-run]

batch.yaml is a list of {path: <note>, <field>: <value>, ...}. Only frontmatter is
touched (so it is legal on knowledge/extracted/ notes); the body is never rewritten.
Every touched note gets `updated: <today>`. Lints the touched files at the end.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lint  # noqa: E402
from kbcore import REPO, load_yaml, set_fields, split_frontmatter  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    items = load_yaml(Path(args.batch)) if Path(args.batch).suffix in (".yaml", ".yml") else []
    if isinstance(items, dict):
        items = items.get("items", [])
    today = dt.date.today().isoformat()
    touched = []
    for item in items:
        path = REPO / item["path"]
        if not path.exists():
            print(f"skip (missing) {item['path']}")
            continue
        text = path.read_text(encoding="utf-8")
        _fm, start = split_frontmatter(text)
        body = text.splitlines(keepends=True)[start:]
        fields = {k: (" ".join(str(v).split()) if k == "abstract" else v)
                  for k, v in item.items() if k != "path" and v not in (None, "")}
        fields["updated"] = today
        new = set_fields(text, fields)
        assert new.splitlines(keepends=True)[-len(body):] == body if body else True, item["path"]
        if not args.dry_run:
            path.write_text(new, encoding="utf-8", newline="")
        touched.append(item["path"])
    print(f"{'would update' if args.dry_run else 'updated'} {len(touched)} note(s)")
    return lint.main(touched) if touched and not args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
