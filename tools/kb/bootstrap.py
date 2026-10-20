"""Initialise the second brain for a new project (run once after forking: /init-brain).

    uv run python tools/kb/bootstrap.py            # set up from project.yaml
    uv run python tools/kb/bootstrap.py --demo     # ...and load the fictional demo project
    uv run python tools/kb/bootstrap.py --no-hook  # skip installing the git pre-commit hook

Idempotent: it never overwrites a register that already has items, and the placeholder
substitution only touches files that still carry {{PROJECT_NAME}}.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kbcore import REGISTERS, REPO, load_yaml, register_names, utf8_stdout  # noqa: E402

PLACEHOLDER = "{{PROJECT_NAME}}"
NAMED_FILES = ["AGENTS.md", "knowledge/index.md"]
LANES = ["specs", "data", "diagrams", "meeting_notes", "correspondence", "prior_deliverables",
         "system_exports"]
DIRS = ["inbox", "knowledge/extracted", "knowledge/curated", "metadata/schemas", "metadata/lineage",
        "artifacts/analysis", "artifacts/design", "artifacts/_imported", "artifacts/adr",
        "artifacts/registers"] + [f"source/{lane}" for lane in LANES]
DEMO = REPO / "examples" / "demo"


def run(*args: str) -> int:
    print(f"$ python {' '.join(args)}")
    return subprocess.call([sys.executable, *args], cwd=REPO)


def name_project(project: dict) -> list[str]:
    name = str(project.get("project_name") or "").strip() or "My Project"
    touched = []
    for f in NAMED_FILES:
        p = REPO / f
        if p.exists() and PLACEHOLDER in (text := p.read_text(encoding="utf-8")):
            p.write_text(text.replace(PLACEHOLDER, name), encoding="utf-8", newline="")
            touched.append(f)
    return touched


def ensure_registers() -> None:
    for name in register_names():
        p = REGISTERS / f"{name}.yaml"
        if not p.exists():
            title = name.replace("_", " ").capitalize()
            p.write_text(f"meta:\n  title: {title}\n  heading: {title}\n  preamble: ''\nitems: []\n",
                         encoding="utf-8", newline="\n")


def load_demo() -> None:
    """Copy the fictional demo project over the skeleton and run the stdlib-only parsers."""
    for src in DEMO.rglob("*"):
        if src.is_file() and src.name != "README.md":
            dst = REPO / src.relative_to(DEMO)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    run("tools/ingest/parse_email.py", "--force")
    run("tools/ingest/build_inventory.py", "--rebuild")


def install_hook() -> None:
    if (REPO / ".git").exists():
        run("tools/kb/hooks/git_pre_commit.py", "--install")
    else:
        print("not a git repository yet: skipped the pre-commit hook (git init, then re-run)")


def main(argv=None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="load the fictional demo project")
    ap.add_argument("--no-hook", action="store_true", help="do not install the git pre-commit hook")
    args = ap.parse_args(argv)

    project = load_yaml(REPO / "project.yaml")
    if args.demo:
        project = load_yaml(DEMO / "project.yaml") or project
    for d in DIRS:
        (REPO / d).mkdir(parents=True, exist_ok=True)
    ensure_registers()
    if args.demo:
        load_demo()
    touched = name_project(project)
    if touched:
        print(f"project name '{project.get('project_name')}' written into: {', '.join(touched)}")
    if not args.no_hook:
        install_hook()
    rc = run("tools/kb/refresh.py")
    print("ready." if rc == 0 else "refresh reported errors: fix them, then run tools/kb/refresh.py")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
