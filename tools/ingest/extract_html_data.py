"""Recover the structured data embedded in self-contained HTML deliverables.

An interactive HTML report (a dependency explorer, a dashboard export...) carries its
payload as JavaScript literals, not as document text. Docling reads such a file as a
near-empty page: hundreds of KB of HTML collapse to 1 KB of Markdown, and the data —
hundreds of objects and edges — silently disappears.

The data is right there in the file, as JSON. This pulls every top-level
`const NAME = [...]` / `{...}` literal out and loads it into DuckDB, so a lineage
question becomes a SQL join instead of an act of faith.

Tables are prefixed `derived_` — this is earlier work product, not primary evidence
(see ADR-0001 and the claims register).

Usage:
    uv run python tools/ingest/extract_html_data.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "kb"))
from kbcore import INV_DB as DB_PATH  # noqa: E402

HTML_DIRS = [REPO / "source" / "prior_deliverables", REPO / "source" / "specs"]
PREFIX = "derived_"

# Only capture substantial payloads; a `const par={...}` of layout constants is noise.
MIN_ROWS = 3

DECL = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([\[{])")


def find_literals(text: str) -> dict[str, object]:
    """Extract each top-level JS array/object literal that parses as JSON."""
    found: dict[str, object] = {}
    for match in DECL.finditer(text):
        name, opener = match.group(1), match.group(2)
        closer = "]" if opener == "[" else "}"
        start = match.start(2)
        depth, in_string, quote, escaped, end = 0, False, "", False, None

        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    in_string = False
                continue
            if ch in "\"'":
                in_string, quote = True, ch
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            continue
        try:
            found[name] = json.loads(text[start:end])
        except json.JSONDecodeError:
            # Not strict JSON (unquoted keys, trailing commas, functions). Skipping is
            # correct: guessing at a repair would fabricate data.
            continue
    return found


def to_rows(value: object) -> list[dict] | None:
    """Normalise a literal into rows, or None if it is not tabular."""
    if isinstance(value, list):
        if all(isinstance(v, dict) for v in value) and len(value) >= MIN_ROWS:
            return value
        return None
    if isinstance(value, dict) and len(value) >= MIN_ROWS:
        # A lookup map {key: label} or {key: {...}} becomes a two/N-column table.
        rows = []
        for key, item in value.items():
            if isinstance(item, dict):
                rows.append({"key": key, **item})
            else:
                rows.append({"key": key, "value": item})
        return rows
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="only files whose name contains this substring")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print("Run tools/ingest/build_inventory.py first.")
        return 1

    import pandas as pd

    con = duckdb.connect(str(DB_PATH))
    loaded = 0

    paths = [
        p
        for d in HTML_DIRS
        if d.exists()
        for p in sorted(d.rglob("*.html"))
        if not args.only or args.only.lower() in p.name.lower()
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        literals = find_literals(text)
        if not literals:
            continue
        stem = re.sub(r"[^0-9a-zA-Z]+", "_", path.stem).strip("_").lower()
        print(f"\n{path.name}")
        for name, value in literals.items():
            rows = to_rows(value)
            if rows is None:
                continue
            frame = pd.json_normalize(rows, max_level=1)
            frame.columns = [
                re.sub(r"[^0-9a-zA-Z]+", "_", str(c)).strip("_").lower() for c in frame.columns
            ]
            # Lists/dicts left in a cell are serialised, never dropped.
            for col in frame.columns:
                frame[col] = frame[col].map(
                    lambda v: json.dumps(v, ensure_ascii=False)
                    if isinstance(v, (list, dict))
                    else v
                )
            frame = frame.astype(object).where(pd.notna(frame), None)
            table = f"{PREFIX}{stem}_{name.lower()}"
            con.register("_staging", frame)
            con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _staging')
            con.unregister("_staging")
            loaded += 1
            print(f"  {name:<12} {len(frame):>5} rows, {len(frame.columns)} cols -> {table}")

    con.close()
    print(f"\n{loaded} table(s) recovered from HTML.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
