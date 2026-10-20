"""Registers: YAML is the source, Markdown views and DuckDB tables are generated.

    python tools/kb/registers.py            # validate, regenerate views, load kb.duckdb
    python tools/kb/registers.py --check    # exit 1 if a view is out of date (pre-commit)
    python tools/kb/registers.py --quiet    # errors only (hooks)

Sources (edit these, by hand or via /capture):
    artifacts/registers/open_points.yaml   OP-nnn
    artifacts/registers/claims.yaml        C-nnn
    artifacts/registers/decisions.yaml     D-nnn

Queries afterwards, e.g.:
    python tools/ingest/query.py "SELECT owner, count(*) FROM kb.reg_open_points
                                  WHERE status = 'open' GROUP BY 1 ORDER BY 2 DESC"
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kbcore import (  # noqa: E402
    GENERATED_MARKER, KB_DB, REGISTERS, evidence_list, load_yaml, schema, utf8_stdout,
)

REG = schema()["registers"]
OP_STATUS = REG["open_points"]["status"]
CLAIM_STATUS = REG["claims"]["status"]
OPEN_LIKE = {"open", "narrowed"}


def marker(src: str) -> str:
    return f"{GENERATED_MARKER}/registers.py from {src} — edit the YAML (/capture), not this file -->"


def fm(title: str, typ: str, updated: str) -> str:
    return (f"---\ntitle: {title}\ntype: {typ}\nstatus: generated\nperspective: mixed\n"
            f"updated: {updated}\n---\n")


def cell(s) -> str:
    return str(s if s is not None else "").replace("\n", "<br>").replace("|", "\\|") if "\\|" not in str(s) else str(s)


def last_updated(data: dict) -> str:
    dates = [str(i.get("updated")) for i in data["items"] if i.get("updated")]
    dates += [str(h.get("date")) for i in data["items"] for h in (i.get("history") or []) if h.get("date")]
    dates.append(str(data["meta"].get("updated", "")))
    return max(d for d in dates if d) if any(dates) else ""


# ---------------------------------------------------------------- validation


def validate(name: str, data: dict) -> list[str]:
    errs = []
    ids = [str(i.get("id")) for i in data.get("items") or []]
    for d in {i for i in ids if ids.count(i) > 1}:
        errs.append(f"{name}: duplicate id {d}")
    pat = REG[name]["id"]
    for item in data.get("items") or []:
        iid = str(item.get("id"))
        if not re.fullmatch(pat, iid):
            errs.append(f"{name}: bad id '{iid}'")
        if name == "open_points":
            if item.get("status") not in OP_STATUS:
                errs.append(f"{iid}: status '{item.get('status')}' not in {OP_STATUS}")
            if not str(item.get("owner") or "").strip():
                errs.append(f"{iid}: owner missing (use TBD)")
        if name == "claims":
            if item.get("status") not in CLAIM_STATUS:
                errs.append(f"{iid}: status '{item.get('status')}' not in {CLAIM_STATUS}")
            bad = [e for e in evidence_list(item.get("evidence")) if e not in schema()["evidence"]]
            if bad:
                errs.append(f"{iid}: evidence {bad} not in schema")
        for h in item.get("history") or []:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(h.get("date", ""))):
                errs.append(f"{iid}: history entry without ISO date")
    return errs


# ---------------------------------------------------------------- views


def render_open_points(data: dict) -> str:
    items = data["items"]
    m = data["meta"]
    out = [fm(m["title"], "decision-log", last_updated(data)), marker("open_points.yaml"), "",
           f"# {m.get('heading', 'Open points')}", "", m["preamble"], ""]
    st = Counter(i["status"] for i in items)
    owners = Counter(i["owner"] for i in items if i["status"] in OPEN_LIKE)
    out += ["## Summary", "",
            "| Status | " + " | ".join(OP_STATUS) + " |",
            "|---|" + "---|" * len(OP_STATUS),
            "| Count | " + " | ".join(str(st.get(s, 0)) for s in OP_STATUS) + " |", "",
            "Open or narrowed, by owner: " + (", ".join(f"{o} {n}" for o, n in owners.most_common())
                                              or "none") + ".", "",
            "## Index", "", "| ID | Open point | Owner | Status | Priority |", "|---|---|---|---|---|"]
    for i in items:
        sid = f"~~{i['id']}~~" if i.get("struck") else i["id"]
        out.append(f"| [{sid}](#{i['id'].lower()}) | {cell(i['title'])} | {cell(i['owner'])} | "
                   f"{i['status']} | {i.get('priority') or ''} |")
    out += ["", "## Details", ""]
    for i in items:
        meta_line = f"**Status:** {i['status']}"
        if i.get("status_note"):
            meta_line += f" ({i['status_note']})"
        meta_line += f" · **Owner:** {i['owner']}"
        if i.get("priority"):
            meta_line += f" · **Priority:** {i['priority']}"
        if i.get("updated"):
            meta_line += f" · **Updated:** {i['updated']}"
        out += [f"### {i['id']}", "", meta_line, "", str(i["text"]).replace("<br>", "\n"), "",
                f"**Impact if unresolved:** {i.get('impact', '')}", ""]
        for h in i.get("history") or []:
            out.append(f"- {h['date']}: {h['note']}")
        if i.get("history"):
            out.append("")
    if m.get("epilogue"):
        out += [m["epilogue"], ""]
    return "\n".join(out).rstrip() + "\n"


def coverage(items: list[dict]) -> list[str]:
    c = Counter(weakest_or_first(i) for i in items)
    total = len(items) or 1
    rows = ["## Coverage", "",
            "Computed by `tools/kb/registers.py` (a composite claim counts at its weakest level).", "",
            "| Evidence level | Claims | % |", "|---|---|---|"]
    for lv in schema()["evidence"]:
        rows.append(f"| {lv} | {c.get(lv, 0)} | {round(100 * c.get(lv, 0) / total)}% |")
    rows.append(f"| **Total** | **{len(items)}** | |")
    return rows


def weakest_or_first(item: dict) -> str:
    levels = evidence_list(item.get("evidence"))
    known = [lv for lv in levels if lv in schema()["evidence"]]
    return max(known, key=schema()["evidence"].index) if known else "unknown"


def render_claims(data: dict) -> str:
    m = data["meta"]
    out = [fm(m["title"], "claims-register", last_updated(data)), marker("claims.yaml"), "",
           f"# {m.get('heading', 'Claims register')}", "", m["preamble"], "",
           "| ID | Claim (one assertion) | Subject | Evidence | Source | Contradicted by | "
           "Design that depends on it | Status |", "|---|---|---|---|---|---|---|---|"]
    for i in data["items"]:
        ev = ", ".join(f"`{e}`" for e in evidence_list(i.get("evidence")))
        status = i["status"] + (f" — {i['status_note']}" if i.get("status_note") else "")
        out.append(f"| {i['id']} | {cell(i['claim'])} | {cell(i.get('object'))} | {ev} | "
                   f"{cell(i.get('source'))} | {cell(i.get('contradicted_by'))} | "
                   f"{cell(i.get('dependency'))} | {cell(status)} |")
    out.append("")
    if m.get("epilogue"):
        out += [m["epilogue"], ""]
    out += coverage(data["items"])
    return "\n".join(out).rstrip() + "\n"


def render_decisions(data: dict) -> str:
    m = data["meta"]
    out = [fm(m["title"], "decision-log", last_updated(data)), marker("decisions.yaml"), "",
           f"# {m.get('heading', 'Decisions')}", "", m["preamble"], "",
           "| ID | Date | Decision | Rationale | Ref |", "|---|---|---|---|---|"]
    for i in data["items"]:
        out.append(f"| {i['id']} | {i['date']} | {cell(i['decision'])} | {cell(i.get('rationale'))} | "
                   f"{cell(i.get('ref'))} |")
    out.append("")
    if m.get("epilogue"):
        out += [m["epilogue"], ""]
    return "\n".join(out).rstrip() + "\n"


RENDER = {"open_points": render_open_points, "claims": render_claims, "decisions": render_decisions}


# ---------------------------------------------------------------- duckdb


def load_db(regs: dict) -> None:
    import duckdb

    KB_DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(KB_DB))

    def insert(table: str, rows: list[tuple]) -> None:
        if rows:
            con.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)

    con.execute("CREATE OR REPLACE TABLE reg_open_points (id VARCHAR PRIMARY KEY, title VARCHAR, "
                "status VARCHAR, status_note VARCHAR, priority VARCHAR, owner VARCHAR, "
                "updated VARCHAR, text VARCHAR, impact VARCHAR)")
    insert("reg_open_points", [
        (i["id"], i["title"], i["status"], i.get("status_note"), i.get("priority"), i["owner"],
         str(i.get("updated") or ""), str(i["text"]), str(i.get("impact") or ""))
        for i in regs["open_points"]["items"]])
    con.execute("CREATE OR REPLACE TABLE reg_claims (id VARCHAR PRIMARY KEY, claim VARCHAR, "
                "object VARCHAR, evidence VARCHAR, weakest_evidence VARCHAR, source VARCHAR, "
                "contradicted_by VARCHAR, dependency VARCHAR, status VARCHAR, status_note VARCHAR)")
    insert("reg_claims", [
        (i["id"], i["claim"], i.get("object"), ", ".join(evidence_list(i.get("evidence"))),
         weakest_or_first(i), i.get("source"), i.get("contradicted_by"), i.get("dependency"),
         i["status"], i.get("status_note")) for i in regs["claims"]["items"]])
    con.execute("CREATE OR REPLACE TABLE reg_decisions (id VARCHAR PRIMARY KEY, date VARCHAR, "
                "decision VARCHAR, rationale VARCHAR, ref VARCHAR)")
    insert("reg_decisions", [
        (i["id"], str(i["date"]), i["decision"], i.get("rationale"), i.get("ref"))
        for i in regs["decisions"]["items"]])
    con.close()


def main(argv=None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args(argv)

    regs, errs = {}, []
    for name in RENDER:
        src = REGISTERS / f"{name}.yaml"
        if not src.exists():
            errs.append(f"missing {src.name}")
            continue
        regs[name] = load_yaml(src)
        meta = regs[name].setdefault("meta", {})
        meta.setdefault("title", name.replace("_", " ").capitalize())
        meta.setdefault("preamble", "")
        regs[name]["items"] = regs[name].get("items") or []
        errs += validate(name, regs[name])
    if errs:
        for e in errs:
            print(f"ERROR registers: {e}")
        return 1

    stale = []
    for name, data in regs.items():
        view = REGISTERS / f"{name}.md"
        text = RENDER[name](data)
        current = view.read_text(encoding="utf-8") if view.exists() else ""
        if current.replace("\r\n", "\n") != text:
            if args.check:
                stale.append(view.name)
            else:
                view.write_text(text, encoding="utf-8", newline="")
    if args.check:
        if stale:
            print(f"ERROR registers: stale view(s) {stale} — run tools/kb/registers.py")
            return 1
        return 0
    if not args.no_db:
        load_db(regs)
    if not args.quiet:
        n = {k: len(v["items"]) for k, v in regs.items()}
        print(f"registers: {n['open_points']} OP, {n['claims']} claims, {n['decisions']} decisions; "
              f"views and kb.duckdb updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
