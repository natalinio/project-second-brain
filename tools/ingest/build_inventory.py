"""Build the structured DB (tools/kb/schema.yaml: structured_db) from the tabular assets in source/.

Every CSV under source/data/ and source/specs/, and every sheet of every workbook there,
becomes one DuckDB table.

The point of this step is that no agent ever has to count, join or eyeball a
spreadsheet again: those questions become SQL.

Usage:
    uv run python tools/ingest/build_inventory.py [--rebuild]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "kb"))
from kbcore import INV_DB as DB_PATH  # noqa: E402

CSV_DIRS = [REPO / "source" / "data", REPO / "source" / "specs"]
XLSX_DIRS = [REPO / "source" / "data", REPO / "source" / "specs"]

# Workbooks recovered from inside other documents by extract_embedded.py. Docling does
# not see these at all, so without this they would be silently lost. Prefixed so it is
# always visible in a query that a table came from an embedded object.
EMBEDDED_XLSX_DIRS = [REPO / "source" / "_extracted"]
EMBEDDED_PREFIX = "embedded_"

# Workbooks that are earlier (often LLM-derived) work products, not primary evidence. They are loaded
# so their claims can be reconciled in SQL, but their tables carry a `derived_` prefix
# so provenance is visible in every query that touches them.
DERIVED_XLSX_DIRS = [REPO / "source" / "prior_deliverables"]
DERIVED_PREFIX = "derived_"

# table name -> 0-based row index used as the header, recorded so a wrong guess is visible
header_notes: dict[str, int] = {}


def identifier(*parts: str) -> str:
    """Make a safe, stable snake_case table name from path/sheet fragments."""
    raw = "_".join(p for p in parts if p)
    name = re.sub(r"[^0-9a-zA-Z]+", "_", raw).strip("_").lower()
    if not name or name[0].isdigit():
        name = f"t_{name}"
    return name


def load_csvs(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Load each CSV, falling back to pandas for files DuckDB's sniffer rejects.

    Project CSVs carry BOMs, multi-line quoted headers and embedded SQL with newlines
    inside fields. DuckDB is faster and types better when it works; pandas is more
    forgiving when it does not. One unreadable file must never abort the whole build.
    """
    import pandas as pd

    loaded = []
    for base in CSV_DIRS:
        for path in sorted(base.rglob("*.csv")):
            table = identifier(path.relative_to(base).with_suffix("").as_posix())
            try:
                # sample_size=-1: infer types from the whole file, not just the first rows.
                con.execute(
                    f'CREATE OR REPLACE TABLE "{table}" AS '
                    "SELECT * FROM read_csv(?, sample_size=-1, union_by_name=true)",
                    [str(path)],
                )
                note = ""
            except duckdb.Error:
                try:
                    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig", engine="python")
                except Exception:  # noqa: BLE001
                    try:
                        frame = pd.read_csv(path, dtype=str, encoding="latin-1", engine="python")
                    except Exception as exc:  # noqa: BLE001
                        print(f"  FAIL  {path.name}: {exc}", file=sys.stderr)
                        continue
                frame.columns = [identifier(str(c)) for c in frame.columns]
                frame = frame.astype(object).where(pd.notna(frame), None)
                con.register("_staging", frame)
                con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _staging')
                con.unregister("_staging")
                note = "  (via pandas fallback)"
            loaded.append(table)
            print(f"  csv   {path.name[:48]:<50} -> {table}{note}")
    return loaded


def detect_header_row(frame) -> int:
    """Find the row that actually holds the column names.

    Project workbooks almost never put the header on row 1: they open with a title,
    a subtitle and a blank line. Reading row 0 as the header yields columns called
    `unnamed_1 … unnamed_11`, which makes the sheet useless for querying.

    Heuristic: among the first rows, the header is the **earliest widest** one. Titles
    and subtitles sit in a single merged cell, so they are narrow; banded headers put
    the real column names on the widest band. Taking the earliest row at the maximum
    width handles both the "title, subtitle, blank, header" shape and a sheet whose
    header genuinely is row 0.

    Data rows are not a threat to this: they are at most as wide as the header. A sparse
    grid of X marks is much narrower, which is why the width of the *following* rows is
    deliberately not part of the test — only that some data follows at all.

    Conservative: falls back to row 0 when unsure.
    """
    widths = [int(frame.iloc[i].notna().sum()) for i in range(len(frame))]
    if not widths:
        return 0

    search = widths[:10]  # a header further down than this is a stacked-table problem
    widest = max(search)
    if widest < 2:
        return 0
    candidate = search.index(widest)
    # Must have something after it, or we just made the last row into column names.
    if not any(w >= 1 for w in widths[candidate + 1 :]):
        return 0
    return candidate


def tidy(frame):
    """Drop all-empty rows and columns left behind by spreadsheet padding."""
    import pandas as pd  # noqa: F401

    return frame.dropna(axis=0, how="all").dropna(axis=1, how="all")


def load_workbooks(
    con: duckdb.DuckDBPyConnection, dirs: list[Path], prefix: str = ""
) -> list[str]:
    """Load every sheet of every workbook as its own table.

    Read through pandas/openpyxl rather than DuckDB's read_xlsx(): the `excel`
    extension is downloaded on first use from extensions.duckdb.org, which restricted
    networks often block. openpyxl keeps this step fully offline.
    """
    import pandas as pd

    loaded: list[str] = []
    seen: set[Path] = set()
    for base in dirs:
        for path in sorted(base.rglob("*.xlsx")):
            if path in seen or path.name.startswith("~$"):
                continue
            seen.add(path)
            try:
                # header=None first: the real header is located, not assumed to be row 0.
                # dtype=str: real-world extracts carry dirty types; typing is decided
                # per-object in knowledge/curated/data_dictionary/, not guessed at load time.
                book = pd.read_excel(
                    path, sheet_name=None, dtype=str, header=None, engine="openpyxl"
                )
            except Exception as exc:  # noqa: BLE001 - one bad workbook must not stop the batch
                print(f"  FAIL  {path.name}: {exc}", file=sys.stderr)
                continue
            for sheet, raw in book.items():
                raw = tidy(raw)
                if raw.empty:
                    print(f"  SKIP  {path.name} [{sheet}]: empty sheet", file=sys.stderr)
                    continue
                header_row = detect_header_row(raw)
                frame = raw.iloc[header_row + 1 :].reset_index(drop=True)
                names: list[str] = []
                used: dict[str, int] = {}
                for i, c in enumerate(raw.iloc[header_row].tolist()):
                    name = identifier(str(c)) if pd.notna(c) and str(c).strip() else f"col_{i}"
                    used[name] = used.get(name, 0) + 1
                    names.append(name if used[name] == 1 else f"{name}_{used[name]}")
                frame.columns = names
                frame = tidy(frame)
                if frame.empty:
                    print(f"  SKIP  {path.name} [{sheet}]: no data rows", file=sys.stderr)
                    continue
                header_notes[prefix + identifier(path.stem, sheet)] = header_row
                table = prefix + identifier(path.stem, sheet)
                # NaN -> NULL: an empty cell must not become the string "nan",
                # or every IS NULL check and outer join downstream is wrong.
                frame = frame.astype(object).where(pd.notna(frame), None)
                con.register("_staging", frame)
                con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _staging')
                con.unregister("_staging")
                loaded.append(table)
                label = f"  xlsx  {path.stem[:30]} [{sheet}]"
                print(f"{label:<58}-> {table}")
    return loaded


def write_catalog(con: duckdb.DuckDBPyConnection) -> None:
    """Emit a versioned Markdown catalog so the schema stays reviewable in Git."""
    rows = con.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'main'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    out = [
        "---",
        "title: DuckDB inventory catalog",
        "type: catalog",
        "status: generated",
        "---",
        "",
        "# DuckDB inventory catalog",
        "",
        "Generated by `tools/ingest/build_inventory.py`. Do not edit by hand.",
    ]
    current = None
    for table, column, dtype in rows:
        if table != current:
            current = table
            count = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            hdr = header_notes.get(table)
            note = f", header taken from row {hdr + 1}" if hdr else ""
            out += ["", f"## `{table}` ({count:,} rows{note})", "", "| Column | Type |", "|---|---|"]
        out.append(f"| `{column}` | {dtype} |")
    path = REPO / "metadata" / "schemas" / "duckdb_catalog.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\ncatalog -> {path.relative_to(REPO)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="delete the database first")
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.rebuild and DB_PATH.exists():
        DB_PATH.unlink()

    con = duckdb.connect(str(DB_PATH))
    print(f"database: {DB_PATH.relative_to(REPO)}\n")
    tables = (
        load_csvs(con)
        + load_workbooks(con, XLSX_DIRS)
        + load_workbooks(con, DERIVED_XLSX_DIRS, DERIVED_PREFIX)
        + load_workbooks(con, EMBEDDED_XLSX_DIRS, EMBEDDED_PREFIX)
    )
    if not tables:
        print("\nNo tabular source files found under source/. Nothing to load.")
        con.close()
        return 0
    write_catalog(con)
    print(f"\n{len(tables)} table(s) loaded.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
