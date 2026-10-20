"""Query the KB graph. Compact Markdown, bounded length: the first grounding step.

    python tools/kb/graph.py about ORDERS_DAILY [--depth 2] [--limit 12]
    python tools/kb/graph.py impact C-001          # who depends on this id / note / object
    python tools/kb/graph.py path ORDERS_RAW SALES_REPORT
    python tools/kb/graph.py find order            # resolve a fuzzy name to graph ids

`about` answers "what do we know about X": lineage up/downstream, the jobs that touch it,
the OPs / claims / decisions that mention it, and the note *sections* that mention it
(path + line range, strongest evidence first) — read those ranges, not whole notes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kbcore import KB_DB, schema, utf8_stdout  # noqa: E402

RANK = {lv: i for i, lv in enumerate(schema()["evidence"])}
ITEM_KINDS = tuple(r.get("kind", n) for n, r in schema()["registers"].items())


def connect():
    import duckdb

    if not KB_DB.exists():
        sys.exit("kb.duckdb not built — run `uv run python tools/kb/refresh.py`")
    return duckdb.connect(str(KB_DB), read_only=True)


def resolve(con, term: str) -> list[str]:
    exact = con.execute("SELECT id FROM nodes WHERE upper(id) = upper(?)", [term]).fetchall()
    if exact:
        return [exact[0][0]]
    al = con.execute("SELECT DISTINCT id FROM aliases WHERE upper(alias) = upper(?)", [term]).fetchall()
    if al:
        return [r[0] for r in al]
    note = con.execute("SELECT id FROM nodes WHERE kind = 'note' AND (id ILIKE ? OR label ILIKE ?) "
                       "LIMIT 5", [f"%{term}%", f"%{term}%"]).fetchall()
    fuzzy = con.execute("SELECT id FROM nodes WHERE kind <> 'note' AND (id ILIKE ? OR label ILIKE ?) "
                        "ORDER BY length(id) LIMIT 8", [f"%{term}%", f"%{term}%"]).fetchall()
    return [r[0] for r in fuzzy] or [r[0] for r in note]


def more(rows: list, limit: int) -> tuple[list, str]:
    return rows[:limit], (f" _(+{len(rows) - limit} more)_" if len(rows) > limit else "")


def lineage(con, nid: str, direction: str, depth: int) -> list[tuple]:
    a, b = ("src", "dst") if direction == "down" else ("dst", "src")
    return con.execute(f"""
        WITH RECURSIVE walk(node, d, weak) AS (
            SELECT {b}, 1, evidence = 'derived-llm' FROM edges WHERE rel = 'feeds' AND {a} = ?
            UNION
            SELECT e.{b}, w.d + 1, w.weak OR e.evidence = 'derived-llm' FROM edges e
            JOIN walk w ON e.{a} = w.node WHERE e.rel = 'feeds' AND w.d < ?)
        SELECT node, min(d) AS d, bool_and(weak) FROM walk WHERE node <> ? GROUP BY node ORDER BY d, node
    """, [nid, depth, nid]).fetchall()


def about(con, nid: str, depth: int, limit: int) -> list[str]:
    kind, label = con.execute("SELECT kind, label FROM nodes WHERE id = ?", [nid]).fetchone()
    out = [f"## {nid} ({kind})" + (f" — {label}" if label and label != nid else "")]
    if kind == "note":
        return out + impact(con, nid, limit)[1:]
    if kind in ITEM_KINDS + ("adr",):
        status, path_ = con.execute("SELECT status, path FROM nodes WHERE id = ?", [nid]).fetchone()
        out.append(f"Status: {status or '-'} · source: `{path_}` (grep `### {nid}` or `| {nid} |`)")
        ents = con.execute("SELECT DISTINCT e.dst, n.kind FROM edges e JOIN nodes n ON n.id = e.dst "
                           "WHERE e.src = ? AND e.rel = 'mentions' ORDER BY 2, 1", [nid]).fetchall()
        if ents:
            rows, tail = more(ents, limit * 2)
            out.append("**Mentions:** " + ", ".join(f"{d} ({k})" for d, k in rows) + tail)
        refs = con.execute("SELECT DISTINCT dst FROM edges WHERE src = ? AND rel = 'cites' ORDER BY 1",
                           [nid]).fetchall()
        if refs:
            out.append("**Cites:** " + ", ".join(r[0] for r in refs[:limit * 2]))
        return out + impact(con, nid, limit)[1:]
    for title, direction in (("Upstream", "up"), ("Downstream", "down")):
        rows, tail = more(lineage(con, nid, direction, depth), limit)
        if rows:
            out.append(f"**{title}** (depth ≤{depth}): " + ", ".join(
                f"{n}" + (f" [{d}]" if d > 1 else "") + ("*" if weak else "") for n, d, weak in rows) + tail)
            if any(weak for _n, _d, weak in rows):
                out.append("_* only via derived-llm edges (unverified)_")
    jobs = con.execute("SELECT DISTINCT src, rel FROM edges WHERE dst = ? AND rel IN ('reads','writes') "
                       "ORDER BY 1", [nid]).fetchall()
    if jobs:
        out.append("**Touched by:** " + ", ".join(f"{j} ({r})" for j, r in jobs[:limit]))
    other = con.execute("""
        SELECT rel, src, dst FROM edges WHERE (src = ? OR dst = ?)
        AND rel NOT IN ('feeds','reads','writes','mentions','cites','defines','is','supersedes')
        ORDER BY 1, 2, 3""", [nid, nid]).fetchall()
    if other:
        rows, tail = more(other, limit)
        out.append("**Relations:** " + "; ".join(f"{s} {r} {d}" for r, s, d in rows) + tail)
    if kind == "job":
        io = con.execute("SELECT rel, dst FROM edges WHERE src = ? AND rel IN ('reads','writes') "
                         "ORDER BY 1, 2", [nid]).fetchall()
        if io:
            out.append("**Job I/O:** " + "; ".join(f"{r} {d}" for r, d in io[:limit * 2]))
    items = con.execute(f"""
        SELECT DISTINCT n.id, n.kind, n.status, n.label FROM edges e JOIN nodes n ON n.id = e.src
        WHERE e.dst = ? AND e.rel = 'mentions' AND n.kind IN ({",".join("?" * len(ITEM_KINDS))})
        ORDER BY n.kind, n.id""", [nid, *ITEM_KINDS]).fetchall()
    if items:
        rows, tail = more(items, limit)
        out.append("**Registers:**" + tail)
        out += [f"- {i} [{k}, {s}] {lbl[:110]}" for i, k, s, lbl in rows]
    defs = con.execute("SELECT path FROM edges WHERE dst = ? AND rel = 'defines'", [nid]).fetchall()
    if defs:
        out.append("**Defined in:** " + ", ".join(f"`{p}`" for (p,) in defs))
    secs = con.execute("""
        SELECT e.path, e.heading, e.line_start, e.line_end, e.n, e.evidence, n.status
        FROM edges e JOIN nodes n ON n.id = e.src
        WHERE e.dst = ? AND e.rel = 'mentions' AND n.kind = 'note'""", [nid]).fetchall()
    # strongest evidence first, superseded last, then most mentions
    secs.sort(key=lambda r: (r[6] == "superseded", RANK.get(r[5], 9), -r[4]))
    if secs:
        rows, tail = more(secs, limit)
        out.append(f"**Sections** ({len(secs)}; strongest evidence first):" + tail)
        out += [f"- `{p}` L{a}-{b} {h[:60]!r} ×{n} [{ev or '-'}{', unchecked' if st == 'extracted' else ''}]"
                for p, h, a, b, n, ev, st in rows]
    return out


def impact(con, nid: str, limit: int) -> list[str]:
    rows = con.execute("""
        WITH RECURSIVE up(node, d) AS (
            SELECT src, 1 FROM edges WHERE dst = ? AND rel IN ('cites','mentions','defines')
            UNION
            SELECT e.src, u.d + 1 FROM edges e JOIN up u ON e.dst = u.node
            WHERE e.rel = 'cites' AND u.d < 2)
        SELECT n.id, n.kind, n.path, n.status, min(u.d) FROM up u JOIN nodes n ON n.id = u.node
        WHERE n.id <> ? GROUP BY ALL ORDER BY 5, 2, 1""", [nid, nid]).fetchall()
    out = [f"## Impact of {nid}: {len(rows)} dependent node(s)"]
    by_kind: dict[str, list] = {}
    for i, k, p, s, d in rows:
        by_kind.setdefault(k, []).append((i, p, s, d))
    for k in ("note", *ITEM_KINDS, "adr"):
        if k in by_kind:
            lst, tail = more(by_kind[k], limit)
            fmt = [f"{p or i}" + (" (indirect)" if d > 1 else "") + (f" [{s}]" if s else "") for i, p, s, d in lst]
            if k == "note":
                out.append(f"**Notes / deliverables:**{tail}")
                out += [f"- `{x}`" for x in fmt]
            else:
                out.append(f"**{k}:** " + ", ".join(i + (" (indirect)" if d > 1 else "") for i, _p, _s, d in lst) + tail)
    return out


def path(con, a: str, b: str) -> list[str]:
    row = con.execute("""
        WITH RECURSIVE walk(node, trail, d) AS (
            SELECT ?, [?], 0
            UNION ALL
            SELECT e.dst, list_append(w.trail, e.dst), w.d + 1 FROM edges e JOIN walk w ON e.src = w.node
            WHERE e.rel = 'feeds' AND w.d < 8 AND NOT list_contains(w.trail, e.dst))
        SELECT trail FROM walk WHERE node = ? ORDER BY d LIMIT 1""", [a, a, b]).fetchone()
    return [" → ".join(row[0])] if row else [f"no feeds path from {a} to {b} (depth ≤8)"]


def main(argv=None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["about", "impact", "path", "find"])
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args(argv)
    con = connect()

    ids = [resolve(con, t) for t in args.terms]
    if args.cmd == "find":
        for t, r in zip(args.terms, ids):
            print(f"{t}: {', '.join(r) or 'no match'}")
        return 0
    if not all(ids):
        missing = [t for t, r in zip(args.terms, ids) if not r]
        print(f"no graph node for {missing}; try `graph.py find <part>` or add an alias in tools/kb/entities.yaml")
        return 1
    if args.cmd == "path":
        print("\n".join(path(con, ids[0][0], ids[1][0])))
        return 0
    first = ids[0]
    if len(first) > 1:
        print(f"_{args.terms[0]!r} matches {len(first)} nodes: {', '.join(first[:10])}; showing {first[0]}_")
    fn = about if args.cmd == "about" else (lambda c, n, d, lim: impact(c, n, lim))
    print("\n".join(fn(con, first[0], args.depth, args.limit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
