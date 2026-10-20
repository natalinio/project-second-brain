"""Catalog of every note + section map, into kb.duckdb; fills the AUTO blocks of the index.

    python tools/kb/build_catalog.py

Tables (query as kb.<name> through tools/ingest/query.py):
    catalog   one row per note: path, title, type, origin, perspective, evidence,
              status, domain, chars, lines, updated, abstract
    sections  one row per heading: path, heading, level, line_start, line_end, chars
              -> read only the section you need:  Read(path, offset=line_start, limit=...)

`<!-- AUTO:name -->` ... `<!-- /AUTO:name -->` blocks (catalog, inventory, status) in
knowledge/index.md and README.md are regenerated; everything outside them is hand-written
and preserved. A file without the markers is left untouched.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kbcore import (  # noqa: E402
    INV_DB, KB_DB, REPO, area_for, evidence_list, iter_md, load_yaml, rel, schema,
    set_fields, split_frontmatter, utf8_stdout,
)

HEADING = re.compile(r"^(#{1,6})\s+(.*)")
COLUMNS = ["path", "title", "type", "origin", "perspective", "evidence", "status", "domain",
           "chars", "lines", "updated", "abstract"]


def groups() -> list[tuple[str, str]]:
    return [(g["prefix"], g["label"]) for g in schema().get("catalog_groups", [])]


def sections(lines: list[str], start: int) -> list[tuple[str, int, int, int]]:
    """(heading, level, line_start, line_end), 1-based lines; fenced code is skipped."""
    found, fence = [], False
    for i in range(start, len(lines)):
        if lines[i].lstrip().startswith("```"):
            fence = not fence
            continue
        m = None if fence else HEADING.match(lines[i])
        if m:
            found.append((m.group(2).strip(), len(m.group(1)), i + 1))
    out = []
    for k, (h, lv, ls) in enumerate(found):
        end = len(lines)
        for h2, lv2, ls2 in found[k + 1:]:
            if lv2 <= lv:
                end = ls2 - 1
                break
        out.append((h, lv, ls, end))
    return out


def collect():
    notes, secs = [], []
    for p in iter_md():
        r = rel(p)
        text = p.read_text(encoding="utf-8", errors="replace")
        fm, start = split_frontmatter(text)
        lines = text.splitlines()
        area = area_for(r)
        notes.append({
            "path": r, "title": str(fm.get("title", p.stem)), "type": str(fm.get("type", "")),
            "origin": str(fm.get("origin", area.get("origin", ""))),
            "perspective": str(fm.get("perspective", area.get("perspective", ""))),
            "evidence": ", ".join(evidence_list(fm.get("evidence"))),
            "status": str(fm.get("status", "")), "domain": str(fm.get("domain", "")),
            "chars": len(text), "lines": len(lines), "updated": str(fm.get("updated", "")),
            "abstract": str(fm.get("abstract", "") or ""),
        })
        for h, lv, ls, le in sections(lines, start):
            secs.append((r, h, lv, ls, le, sum(len(x) + 1 for x in lines[ls - 1:le])))
    return notes, secs


def load_db(notes, secs) -> None:
    import duckdb

    KB_DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(KB_DB))
    con.execute("CREATE OR REPLACE TABLE catalog (" + ", ".join(
        f"{c} {'INTEGER' if c in ('chars', 'lines') else 'VARCHAR'}" for c in COLUMNS) + ")")
    if notes:
        con.executemany(f"INSERT INTO catalog VALUES ({','.join('?' * len(COLUMNS))})",
                        [tuple(n[c] for c in COLUMNS) for n in notes])
    con.execute("CREATE OR REPLACE TABLE sections (path VARCHAR, heading VARCHAR, level INTEGER, "
                "line_start INTEGER, line_end INTEGER, chars INTEGER)")
    if secs:
        con.executemany("INSERT INTO sections VALUES (?,?,?,?,?,?)", secs)
    con.close()


# ---------------------------------------------------------------- AUTO blocks


def block_catalog(notes) -> str:
    out = []
    used = set()
    for prefix, label in groups():
        rows = [n for n in notes if n["path"].startswith(prefix) and n["path"] not in used]
        if not rows:
            continue
        used.update(n["path"] for n in rows)
        out += [f"### {label}", "", "| Note | Evidence | Status | KB | What it is |", "|---|---|---|---|---|"]
        for n in rows:
            link = n["path"][len("knowledge/"):]
            what = n["abstract"] or n["title"]
            what = re.sub(r"\s+", " ", what)
            what = what if len(what) <= 160 else what[:157] + "..."
            out.append(f"| [{Path(n['path']).stem}]({link}) | {n['evidence']} | {n['status']} | "
                       f"{round(n['chars'] / 1000)} | {what.replace('|', '/')} |")
        out.append("")
    return ("\n".join(out).rstrip()
            or "_No knowledge notes yet: drop material in `inbox/` and run `/ingest`._")


def block_inventory() -> str:
    import duckdb

    if not INV_DB.exists():
        return f"_`{rel(INV_DB)}` not built — run `uv run python tools/ingest/build_inventory.py`_"
    con = duckdb.connect(str(INV_DB), read_only=True)
    total = con.execute("SELECT count(*) FROM duckdb_tables()").fetchone()[0]
    fam = dict(con.execute(
        "SELECT CASE WHEN table_name LIKE 'embedded_%' THEN 'embedded_*' "
        "WHEN table_name LIKE 'derived_%' THEN 'derived_*' ELSE 'other' END, count(*) "
        "FROM duckdb_tables() GROUP BY 1").fetchall())
    out = [f"**{total} tables** in `{rel(INV_DB)}` "
           f"({fam.get('embedded_*', 0)} `embedded_*` recovered from embedded workbooks, "
           f"{fam.get('derived_*', 0)} `derived_*` from prior deliverables — **not evidence**).", "",
           "| Table | Rows | What it is |", "|---|---|---|"]
    key = load_yaml(Path(__file__).parent / "index_key_tables.yaml").get("key_tables") or []
    if not key:
        out = out[:1] + ["", "_List the tables worth knowing in `tools/kb/index_key_tables.yaml`._"]
    for k in key:
        try:
            n = con.execute(f'SELECT count(*) FROM "{k["table"]}"').fetchone()[0]
            out.append(f"| `{k['table']}` | {n:,} | {k['what']} |")
        except duckdb.Error:
            out.append(f"| `{k['table']}` | **missing** | {k['what']} |")
    con.close()
    return "\n".join(out)


def block_status(notes) -> str:
    import duckdb

    kn = [n for n in notes if n["path"].startswith("knowledge/") and n["type"] != "index"]
    st = Counter((n["origin"], n["status"]) for n in kn)
    con = duckdb.connect(str(KB_DB), read_only=True)
    op = dict(con.execute("SELECT status, count(*) FROM reg_open_points GROUP BY 1").fetchall())
    cl = dict(con.execute("SELECT weakest_evidence, count(*) FROM reg_claims GROUP BY 1").fetchall())
    nd = con.execute("SELECT count(*) FROM reg_decisions").fetchone()[0]
    con.close()
    ex = [n for n in kn if n["origin"] == "extracted"]
    checked = sum(1 for n in ex if n["status"] == "checked")
    big = [n for n in kn if n["chars"] > schema()["abstract_threshold"] and not n["abstract"]]
    return "\n".join([
        "| Measure | Value |", "|---|---|",
        f"| Knowledge notes | {len(kn)} ({sum(1 for n in kn if n['origin'] == 'curated')} curated, {len(ex)} extracted) |",
        f"| Extractions checked | {checked} / {len(ex)} |",
        f"| Large notes without abstract | {len(big)} |",
        "| Open points | " + (", ".join(f"{op.get(s, 0)} {s}" for s in
                                        schema()["registers"]["open_points"]["status"]) if op else "none") + " |",
        "| Claims (weakest evidence) | " + (", ".join(f"{k} {v}" for k, v in sorted(cl.items())) or "none") + " |",
        f"| Decisions | {nd} |",
        "| Knowledge status | " + (", ".join(f"{o}/{s} {c}" for (o, s), c in sorted(st.items())) or "none") + " |",
    ])


def fill(path: Path, blocks: dict[str, str]) -> bool:
    text = path.read_text(encoding="utf-8")
    new = text
    for name, content in blocks.items():
        pat = re.compile(rf"(<!-- AUTO:{name} -->)(.*?)(<!-- /AUTO:{name} -->)", re.S)
        if pat.search(new):
            new = pat.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", new)
    if new != text:
        fm, _ = split_frontmatter(new)
        if fm:
            import datetime as dt

            new = set_fields(new, {"updated": dt.date.today().isoformat()})
        path.write_text(new, encoding="utf-8", newline="")
        return True
    return False


def main(argv=None) -> int:
    utf8_stdout()
    notes, secs = collect()
    load_db(notes, secs)
    changed = []
    blocks = {"catalog": block_catalog(notes), "inventory": block_inventory(),
              "status": block_status(notes)}
    for target in (REPO / "knowledge" / "index.md", REPO / "README.md"):
        if target.exists() and fill(target, blocks):
            changed.append(rel(target))
    print(f"catalog: {len(notes)} notes, {len(secs)} sections"
          + (f"; regenerated {', '.join(changed)}" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
