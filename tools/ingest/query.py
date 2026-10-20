"""Run read-only SQL against the structured DB and the brain index; print Markdown.

This is the deterministic grounding path: any question about counts, joins or
dependencies in tabular material is answered here, never by reading a spreadsheet.

    uv run python tools/ingest/query.py --tables
    uv run python tools/ingest/query.py "SELECT * FROM orders_sample LIMIT 20"
    uv run python tools/ingest/query.py "SELECT id, title FROM kb.reg_open_points WHERE status = 'open'"

The structured DB (schema.yaml: structured_db, built by build_inventory.py) is the default
schema; the brain index metadata/kb.duckdb (registers, catalog, sections, graph) is attached
as schema `kb`. Either may be missing: the other still works.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kb"))
from kbcore import INV_DB, KB_DB, utf8_stdout  # noqa: E402


def main() -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("sql", nargs="?", help="SQL to execute")
    parser.add_argument("--tables", action="store_true", help="list tables and row counts")
    parser.add_argument("--limit", type=int, default=200, help="max rows printed")
    args = parser.parse_args()

    if not INV_DB.exists() and not KB_DB.exists():
        print("No database yet - run `uv run python tools/kb/refresh.py` "
              "(and tools/ingest/build_inventory.py for tabular material).")
        return 1

    # read_only: both databases are derived state, rebuilt from source and never edited.
    con = duckdb.connect(str(INV_DB), read_only=True) if INV_DB.exists() else duckdb.connect()
    if KB_DB.exists():
        kb_path = KB_DB.as_posix().replace("'", "''")
        con.execute(f"ATTACH '{kb_path}' AS kb (READ_ONLY)")

    if args.tables:
        names = [row[0] for row in con.execute("SHOW TABLES").fetchall()] if INV_DB.exists() else []
        if KB_DB.exists():
            names += [f"kb.{r[0]}" for r in con.execute(
                "SELECT table_name FROM duckdb_tables() WHERE database_name = 'kb' ORDER BY 1").fetchall()]
        if not names:
            print("_(no tables)_")
            return 0
        print("| Table | Rows |")
        print("|---|---|")
        for name in names:
            q = name if name.startswith("kb.") else f"\"{name}\""
            n = con.execute(f"SELECT count(*) FROM {q}").fetchone()[0]
            print(f"| `{name}` | {n:,} |")
        return 0

    if not args.sql:
        parser.error("provide a SQL statement or --tables")

    df = con.execute(args.sql).fetchdf()
    if df.empty:
        print("_(0 rows)_")
        return 0
    print(df.head(args.limit).to_markdown(index=False))
    suffix = f", showing first {args.limit}" if len(df) > args.limit else ""
    print(f"\n_{len(df):,} row(s){suffix}_")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
