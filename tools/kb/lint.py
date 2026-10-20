"""Lint the KB against tools/kb/schema.yaml. Errors block; warnings are a backlog.

    python tools/kb/lint.py                 # whole KB: errors listed, warnings counted
    python tools/kb/lint.py --warnings      # also list every warning
    python tools/kb/lint.py FILE [FILE...]  # only these files (used by the hooks)

Output is deliberately terse: one line per finding, so an agent reading it spends
tokens on fixing, not on parsing.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kbcore import (  # noqa: E402
    ADR_DIR, GENERATED_MARKER, REGISTERS, REPO, SKIP_PREFIXES, adr_id, area_for, evidence_list,
    evidence_rank, id_regex, iter_md, load_yaml, register_names, rel, schema, split_frontmatter,
    top, utf8_stdout,
)

ROOT_DOCS = ("AGENTS.md", "CLAUDE.md", "README.md", "PREREQUISITES.md", "inbox/README.md")
EXAMPLE_PATHS = re.compile(r"example|/foo\.md|<[^>]+>|NNN|YYYY")
LINK_RE = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
PATH_RE = re.compile(r"(?<![\w/.-])((?:knowledge|artifacts|docs|tools|metadata)/[\w./-]+\.(?:md|html|py|yaml|csv|json))")


def historical_paths() -> set[str]:
    """Every path that ever existed in git, mapped onto the current layout.

    A dated record (decision log, reconciliation) may cite a file deleted later: that
    is history, not a broken reference. One git call for the whole repo.
    """
    import subprocess

    try:
        out = subprocess.run(["git", "log", "--all", "--name-only", "--format="], cwd=REPO,
                             capture_output=True, text=True, encoding="utf-8").stdout
    except OSError:
        return set()
    return {p for p in out.splitlines() if p}


class LazyHistory:
    """Defers the git call until a missing path actually needs checking."""

    def __init__(self):
        self._paths: set[str] | None = None

    def __contains__(self, item: str) -> bool:
        if self._paths is None:
            self._paths = historical_paths()
        return item in self._paths


def known_ids() -> set[str]:
    ids: set[str] = set()
    for name in register_names():
        ids.update(str(i["id"]) for i in load_yaml(REGISTERS / f"{name}.yaml").get("items") or [])
    ids.update(a for a in (adr_id(p) for p in ADR_DIR.glob("ADR-*.md")) if a)
    return ids


def lint_file(path: Path, ids: set[str], errors: list, warnings: list, history) -> None:
    r = rel(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body_start = split_frontmatter(text)
    body = "\n".join(text.splitlines()[body_start:])
    area = area_for(r)
    sch = schema()

    def err(rule, msg):
        errors.append(f"{r}: {rule}: {msg}")

    def warn(rule, msg):
        warnings.append((rule, f"{r}: {msg}"))

    if r not in ROOT_DOCS:
        if not fm:
            err("frontmatter", "missing")
            return
        req = [k for k in sch["required"].get(top(r), []) if not (k == "evidence" and fm.get("type") == "index")]
        missing = [k for k in req if fm.get(k) in (None, "")]
        if missing:
            err("required", ", ".join(missing))

        levels = evidence_list(fm.get("evidence"))
        bad = [lv for lv in levels if lv not in sch["evidence"]]
        if bad:
            err("evidence", f"not in schema: {bad}")

        origin = area.get("origin")
        bucket = origin if origin in ("extracted", "curated") else ("artifacts" if top(r) == "artifacts" else None)
        st = str(fm.get("status", ""))
        if bucket and st and st not in sch["status"][bucket]:
            err("status", f"'{st}' not allowed in {bucket}: {sch['status'][bucket]}")
        if top(r) == "knowledge" and r != "knowledge/index.md" and fm.get("origin") != origin:
            err("origin", f"is '{fm.get('origin')}', folder says '{origin}'")
        if area.get("evidence") and levels != [area["evidence"]]:
            err("evidence", f"this folder only holds '{area['evidence']}'")

        expected = sch["type_evidence"].get(str(fm.get("type")))
        if expected and levels and not fm.get("evidence_note"):
            stronger = [lv for lv in levels if evidence_rank(lv) < evidence_rank(expected[0])]
            if stronger:
                err("type-evidence", f"a {fm.get('type')} is {expected[0]}; {stronger} needs evidence_note")

        if len(text) > sch["abstract_threshold"] and not fm.get("abstract") and st != "generated":
            warn("abstract", f"{len(text) // 1000} KB without abstract")
        if st == "extracted":
            warn("unchecked", "extraction not yet checked (/review-note)")
        if top(r) == "artifacts" and GENERATED_MARKER not in text:
            for pat in sch["legend_patterns"]:
                if re.search(pat, text):
                    warn("legend", "ad-hoc evidence legend: move assumptions to the claims register")
                    break

    # references -----------------------------------------------------------
    base = path.parent
    for m in LINK_RE.finditer(body if fm else text):
        target = m.group(1)
        if re.match(r"^[a-z]+:|^/|^\{", target) or EXAMPLE_PATHS.search(target):
            continue
        resolved = os.path.normpath(base / target)
        if not os.path.exists(resolved):
            try:
                as_repo = Path(resolved).resolve().relative_to(REPO).as_posix()
            except ValueError:
                as_repo = ""
            if as_repo in history:
                warn("historical", f"link to a since-deleted file: {target}")
            else:
                err("link", f"broken: {target}")
    generated = set(sch.get("generated_paths", []))
    for m in PATH_RE.finditer(text):
        p = m.group(1).rstrip(".")
        if EXAMPLE_PATHS.search(p) or p in generated:
            continue
        if not (REPO / p).exists():
            if p in history:
                warn("historical", f"cites a since-deleted file: {p}")
            else:
                err("path", f"missing: {p}")
    for m in id_regex().finditer(body if fm else text):
        if m.group(1) not in ids and ids:
            fam = m.group(1).split("-")[0]
            if any(i.startswith(fam + "-") for i in ids):
                err("id", f"unknown {m.group(1)}")


def main(argv=None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--warnings", action="store_true")
    args = ap.parse_args(argv)

    if args.files:
        paths = [Path(f) if Path(f).is_absolute() else REPO / f for f in args.files]
        paths = [p for p in paths if p.suffix == ".md" and p.exists()]
    else:
        paths = iter_md() + [REPO / d for d in ROOT_DOCS if (REPO / d).exists()]
    ids = known_ids()
    history = LazyHistory()
    errors: list[str] = []
    warnings: list[tuple[str, str]] = []
    for p in paths:
        if rel(p).startswith(SKIP_PREFIXES):
            continue
        lint_file(p, ids, errors, warnings, history)

    for e in errors:
        print(f"ERROR {e}")
    if args.warnings:
        for _rule, w in warnings:
            print(f"warn  {w}")
    if not args.files or args.warnings:
        counts = Counter(rule for rule, _ in warnings)
        summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"
        print(f"{len(paths)} file(s): {len(errors)} error(s); warnings: {summary}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
