"""Deterministic knowledge graph of the KB, into kb.duckdb (tables `nodes`, `edges`, `aliases`).

No LLM, no embeddings: every node and edge comes from a structured source or an exact
identifier match, so the graph is reproducible and never stronger than its evidence.

    python tools/kb/build_graph.py

Nodes  (id, kind, label, path, evidence, status)
  note:<path>            every Markdown note (catalog)
  OP-nnn / C-nnn / D-nnn register items        ADR-nnnn  ADRs
  <IDENTIFIER>           objects declared by tools/kb/graph_sources.yaml (tables, jobs,
                         files, services, components...: whatever your project has)
  <CONCEPT>              systems / parties / concepts from tools/kb/entities.yaml
Edges  (src, dst, rel, evidence, path, heading, line_start, line_end, n, attr)
  mentions   note|item -> entity   (per section: heading + line range = what to Read)
  cites      note|item -> note|item (paths and register/ADR ids in the text)
  defines    note -> the object named in its `defines:` frontmatter field
  <rel>      object -> object       (declared in graph_sources.yaml: feeds, reads, writes,
                                     calls, owns... any verb you choose)
  supersedes note -> note
Edge evidence is the evidence of the source it was read from.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_catalog import sections  # noqa: E402
from kbcore import (  # noqa: E402
    ADR_DIR, INV_DB, KB_DB, REGISTERS, REPO, adr_id, evidence_list, id_regex, iter_md, load_yaml,
    register_names, rel, schema, split_frontmatter, utf8_stdout, weakest,
)

HERE = Path(__file__).parent
PATH_RE = re.compile(r"(?<![\w/.-])((?:knowledge|artifacts|docs)/[\w./-]+\.md)")


def _ident_cfg() -> dict:
    return schema().get("identifier", {})


def stop_words() -> set[str]:
    return {str(s).upper() for s in _ident_cfg().get("stop", []) if s is not None}


def short(name: str) -> tuple[str, set[str]]:
    """Canonical id + aliases for an identifier as written in a structured source.

    `SCHEMA.TABLE` and `system::path/NAME` are reduced to their last segment; a file name
    `STEM.YYYYMMDD.ext` also yields its stem as an alias.
    """
    raw = name.strip()
    raw = re.sub(r"\s+\([A-Za-z. ]+\)$", "", raw)  # trailing hint in parentheses: 'ORDERS (sales)'
    aliases = {raw}
    s = re.split(r"::|/", raw)[-1] or raw
    if re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+", s):  # SCHEMA.TABLE
        s = s.split(".")[-1]
    aliases.add(s)
    m = re.match(r"^([A-Z][A-Z0-9_]{3,})\.", s)  # file stem: ORDERS.20260101.csv
    if m and m.group(1) not in stop_words():
        aliases.add(m.group(1))
    return s, aliases


def usable(alias: str) -> bool:
    cfg = _ident_cfg()
    return (len(alias) >= cfg.get("min_length", 5) and alias.upper() not in stop_words()
            and " " not in alias and re.fullmatch(cfg.get("pattern", r".+"), alias) is not None)


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[tuple] = []
        self.alias: dict[str, str] = {}

    def node(self, nid, kind, label="", path="", evidence="", status=""):
        n = self.nodes.setdefault(nid, {"kind": kind, "label": label, "path": path,
                                        "evidence": evidence, "status": status})
        for k, v in (("label", label), ("path", path), ("evidence", evidence), ("status", status)):
            if v and not n[k]:
                n[k] = v
        if n["kind"] in ("object", "") and kind not in ("object", ""):
            n["kind"] = kind
        return nid

    def entity(self, name: str, kind: str, label: str = "") -> str | None:
        if not name or not str(name).strip():
            return None
        sid, aliases = short(str(name))
        if not sid:
            return None
        self.node(sid, kind, label or (str(name) if str(name) != sid else ""))
        for a in aliases:
            self.alias.setdefault(a, sid)
        return sid

    def edge(self, src, dst, rel, evidence="", path="", heading="", ls=0, le=0, n=1, attr=""):
        if src and dst and src != dst:
            self.edges.append((src, dst, rel, evidence, path, heading, ls, le, n, attr))


# ---------------------------------------------------------------- structured sources


def _rows(src: dict) -> list[dict]:
    """Rows of one graph source as dicts. Missing files/tables are skipped with a note."""
    if src.get("type", "csv") == "csv":
        p = REPO / src["path"]
        if not p.exists():
            print(f"graph: source '{src.get('name', src['path'])}' skipped, {src['path']} not found")
            return []
        with p.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    if src["type"] == "sql":
        import duckdb

        if not INV_DB.exists():
            print(f"graph: source '{src.get('name')}' skipped, {rel(INV_DB)} not built")
            return []
        con = duckdb.connect(str(INV_DB), read_only=True)
        try:
            cur = con.execute(src["query"])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except duckdb.Error as exc:
            print(f"graph: source '{src.get('name')}' skipped: {exc}")
            return []
        finally:
            con.close()
    raise ValueError(f"graph source type must be csv or sql: {src}")


def _values(row: dict, col: str, split: str | None) -> list[str]:
    v = row.get(col)
    if v is None or str(v).strip() == "":
        return []
    return [x.strip() for x in re.split(split, str(v))] if split else [str(v).strip()]


def from_sources(g: Graph) -> None:
    """Nodes and edges declared in tools/kb/graph_sources.yaml (see the comments there)."""
    for src in load_yaml(HERE / "graph_sources.yaml").get("sources") or []:
        where = src.get("path") or src.get("name", "sql")
        ev = src.get("evidence", "primary-doc")
        node_cfg = {n["column"]: n for n in src.get("nodes", [])}
        for row in _rows(src):
            ids: dict[str, list[str]] = {}
            for col, cfg in node_cfg.items():
                label = str(row.get(cfg["label"]) or "") if cfg.get("label") else ""
                ids[col] = [i for i in (g.entity(v, cfg.get("kind", "object"), label)
                                        for v in _values(row, col, cfg.get("split"))) if i]
            for e in src.get("edges", []):
                attr = " · ".join(str(row[c]) for c in e.get("attr", []) if row.get(c))
                for s in ids.get(e["src"], []):
                    for d in ids.get(e["dst"], []):
                        g.edge(s, d, e["rel"], e.get("evidence", ev), where, attr=attr)


def concepts(g: Graph) -> list[tuple[re.Pattern, str]]:
    pats = []
    for c in load_yaml(HERE / "entities.yaml").get("concepts") or []:
        g.node(c["id"], c.get("kind", "concept"), c["aliases"][0])
        alt = "|".join(re.escape(a) for a in sorted(c["aliases"], key=len, reverse=True))
        pats.append((re.compile(rf"(?<![\w/])(?:{alt})(?![\w])", re.I), c["id"]))
    return pats


def ident_matcher(g: Graph) -> tuple[re.Pattern | None, dict]:
    lookup = {a: sid for a, sid in g.alias.items() if usable(a)}
    if not lookup:
        return None, {}
    alt = "|".join(re.escape(a) for a in sorted(lookup, key=len, reverse=True))
    return re.compile(rf"(?<![\w/.])(?:{alt})(?![\w])"), lookup


# ---------------------------------------------------------------- text scanning


def leaf_sections(lines: list[str], start: int) -> list[tuple[str, int, int]]:
    """(heading, line_start, line_end) where each range stops at the NEXT heading of any
    level, so a mention is attributed to the innermost section only (no double counting,
    and the narrowest range to Read). Text before the first heading is its own chunk."""
    secs = sections(lines, start)
    out = []
    first = secs[0][2] if secs else len(lines) + 1
    if first - 1 > start:
        out.append(("(preamble)", start + 1, first - 1))
    for k, (h, _lv, ls, _le) in enumerate(secs):
        end = secs[k + 1][2] - 1 if k + 1 < len(secs) else len(lines)
        out.append((h, ls, end))
    return out


def scan(g, src, text_lines, start, path, evidence, ident, lookup, cpats, path_ids):
    for heading, ls, le in leaf_sections(text_lines, start):
        chunk = "\n".join(text_lines[ls - 1:le])
        hits = defaultdict(int)
        if ident is not None:
            for m in ident.finditer(chunk):
                hits[lookup[m.group(0)]] += 1
        for pat, cid in cpats:
            n = len(pat.findall(chunk))
            if n:
                hits[cid] += n
        for eid, n in hits.items():
            g.edge(src, eid, "mentions", evidence, path, heading, ls, le, n)
        for m in id_regex().finditer(chunk):
            g.edge(src, m.group(1), "cites", evidence, path, heading, ls, le)
        for m in PATH_RE.finditer(chunk):
            target = path_ids.get(m.group(1))
            if target:
                g.edge(src, target, "cites", evidence, path, heading, ls, le)


def build() -> Graph:
    g = Graph()
    from_sources(g)
    cpats = concepts(g)
    ident, lookup = ident_matcher(g)

    notes = iter_md()
    path_ids = {rel(p): f"note:{rel(p)}" for p in notes}
    regs = {n: load_yaml(REGISTERS / f"{n}.yaml") for n in register_names()
            if (REGISTERS / f"{n}.yaml").exists()}
    view_names = {rel(REGISTERS / f"{n}.md") for n in regs}

    for p in notes:
        r = rel(p)
        if r in view_names:
            continue  # the items themselves are nodes; the generated view would double-count
        text = p.read_text(encoding="utf-8", errors="replace")
        fm, start = split_frontmatter(text)
        ev = weakest(evidence_list(fm.get("evidence"))) or ""
        nid = g.node(path_ids[r], "note", str(fm.get("title", p.stem)), r, ev, str(fm.get("status", "")))
        lines = text.splitlines()
        scan(g, nid, lines, start, r, ev, ident, lookup, cpats, path_ids)
        for target in evidence_list(fm.get("defines")):
            g.edge(nid, g.entity(target, "object"), "defines", ev, r)
        if fm.get("superseded_by"):
            g.edge(path_ids.get(str(fm["superseded_by"])), nid, "supersedes", ev, r)

    for p in ADR_DIR.glob("ADR-*.md"):
        aid = adr_id(p)
        if aid:
            g.node(aid, "adr", p.stem, rel(p))
            g.edge(aid, path_ids.get(rel(p)), "is", "", rel(p))

    kinds = {n: c.get("kind", n) for n, c in schema()["registers"].items()}
    for name, data in regs.items():
        view = rel(REGISTERS / f"{name}.md")
        for item in data.get("items") or []:
            iid = item["id"]
            label = item.get("title") or item.get("claim") or item.get("decision") or ""
            ev = weakest(evidence_list(item.get("evidence"))) or ""
            g.node(iid, kinds[name], str(label)[:200], view, ev, str(item.get("status", "")))
            text = "\n".join(str(v) for k, v in item.items()
                             if k not in ("id", "history", "status", "owner", "priority") and v)
            lines = ["# x"] + text.splitlines()
            scan(g, iid, lines, 0, view, ev, ident, lookup, cpats, path_ids)
    # drop dangling id cites (an id mentioned that no register defines)
    g.edges = [e for e in g.edges if e[1] in g.nodes and e[0] in g.nodes]
    return g


def save(g: Graph) -> None:
    import duckdb

    KB_DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(KB_DB))
    con.execute("CREATE OR REPLACE TABLE nodes (id VARCHAR PRIMARY KEY, kind VARCHAR, label VARCHAR, "
                "path VARCHAR, evidence VARCHAR, status VARCHAR)")
    if g.nodes:
        con.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?)",
                        [(k, v["kind"], v["label"], v["path"], v["evidence"], v["status"])
                         for k, v in g.nodes.items()])
    con.execute("CREATE OR REPLACE TABLE edges (src VARCHAR, dst VARCHAR, rel VARCHAR, evidence VARCHAR, "
                "path VARCHAR, heading VARCHAR, line_start INTEGER, line_end INTEGER, n INTEGER, attr VARCHAR)")
    if g.edges:
        con.executemany("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?)", g.edges)
    con.execute("CREATE OR REPLACE TABLE aliases (alias VARCHAR, id VARCHAR)")
    if g.alias:
        con.executemany("INSERT INTO aliases VALUES (?,?)", list(g.alias.items()))
    con.close()


def main(argv=None) -> int:
    utf8_stdout()
    g = build()
    save(g)
    kinds = defaultdict(int)
    for v in g.nodes.values():
        kinds[v["kind"]] += 1
    rels = defaultdict(int)
    for e in g.edges:
        rels[e[2]] += 1
    print(f"graph: {len(g.nodes)} nodes ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}); "
          f"{len(g.edges)} edges ({', '.join(f'{k} {v}' for k, v in sorted(rels.items()))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
