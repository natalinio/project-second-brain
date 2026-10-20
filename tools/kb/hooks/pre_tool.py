"""PreToolUse hook (Claude Code and GitHub Copilot): enforce the KB write contract.

Rules (AGENTS.md §0), with the folders taken from tools/kb/schema.yaml `protected:`:
  * immutable folders (source/) are never written (MANIFEST.md excepted)
  * body-locked folders (knowledge/extracted/) and accepted ADRs: frontmatter may change,
    the body may not
  * generated register views are not edited by hand: edit the YAML

The shell check is a guard rail against accidents, not a sandbox: it catches the usual
destructive verbs, redirections and moves on POSIX shells and PowerShell, / or \\ paths.
Payload formats and answers: see agent_io.py.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_io import Call, deny, read_call  # noqa: E402
from kbcore import GENERATED_MARKER, REPO, schema, split_frontmatter  # noqa: E402

PROT = schema().get("protected", {})
IMMUTABLE = tuple(PROT.get("immutable", ["source/"]))
IMMUTABLE_EXCEPT = set(PROT.get("immutable_except", ["source/MANIFEST.md"]))
BODY_LOCKED = tuple(PROT.get("body_locked", ["knowledge/extracted/"]))
ADR_DIR = PROT.get("accepted_adr_dir", "artifacts/adr/")


def _dirs(prefixes) -> str:
    return "|".join(re.escape(p.rstrip("/")) for p in prefixes)


# a protected folder, as "source/..." or as the bare folder name ("rm -rf source")
_END = r"(?:/|(?=[\s\"'`;|&)]|$))"
PROTECTED = re.compile(rf"(?<![\w.-])({_dirs(IMMUTABLE + BODY_LOCKED)}){_END}")
LOCKED_DEST = re.compile(rf"(?<![\w.-])({_dirs(BODY_LOCKED)}){_END}")
DESTRUCTIVE = re.compile(
    r"\b(rm|rmdir|del|erase|rd|truncate|shred|unlink|tee)\b|sed\s+-i|perl\s+-i|"
    r"\bgit\s+(rm|checkout\s+--|restore|clean)\b|"
    r"Remove-Item|Set-Content|Add-Content|Out-File|Clear-Content|Rename-Item|New-Item\b.*-Force",
    re.I)
REDIRECT_INTO = re.compile(rf">{{1,2}}\s*[\"']?[^\s\"']*(?<![\w-])({_dirs(IMMUTABLE + BODY_LOCKED)})/")
MOVE = re.compile(r"\s*(?:git\s+)?(mv|move|ren|rename|Move-Item|cp|copy|Copy-Item)\s+(.*)", re.I)


def relpath(p: str) -> str | None:
    if not p:
        return None
    p = re.sub(r"^file:/+", "", p)
    path = Path(p)
    if not path.is_absolute():
        path = REPO / path
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def frontmatter_only(path: Path, olds: list[str]) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    _fm, body_start = split_frontmatter(text)
    if not body_start or not olds:
        return False
    head = "".join(text.splitlines(keepends=True)[:body_start])
    return all(o and o in head and text.count(o) == 1 for o in olds)


def check_path(call: Call, r: str) -> str | None:
    """Reason to deny a write to repo path `r`, or None."""
    if r.startswith(IMMUTABLE) and r not in IMMUTABLE_EXCEPT:
        return f"{r.split('/')[0]}/ is immutable raw material. Add new files via inbox/ triage (/ingest)."
    path = REPO / r
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if GENERATED_MARKER in text:
        return f"{r} is generated. Edit the YAML in artifacts/registers/ (/capture); views regenerate."
    is_adr = bool(r.startswith(ADR_DIR) and re.search(r"^status:\s*accepted\s*$", text, re.M))
    if r.startswith(BODY_LOCKED) or is_adr:
        if call.kind == "write" and not call.whole and frontmatter_only(path, call.olds):
            return None
        what = "an accepted ADR (supersede it with a new ADR)" if is_adr else \
            "an extracted note (corrections and syntheses go to knowledge/curated/)"
        return f"{r} is {what}. Only its frontmatter may change, with a targeted string replacement."
    return None


def _args(text: str) -> list[str]:
    try:
        parts = shlex.split(text, posix=True)
    except ValueError:
        parts = text.split()
    return [a for a in parts if not a.startswith("-")]


def check_shell(cmd: str) -> str | None:
    cmd = cmd.replace("\\", "/")  # Windows paths: knowledge\extracted\x.md
    for seg in re.split(r"&&|\|\||;|\n|\|", cmd):
        if not PROTECTED.search(seg):
            continue
        if DESTRUCTIVE.search(seg) or REDIRECT_INTO.search(seg):
            return ("shell command would modify a protected folder "
                    f"({', '.join(IMMUTABLE + BODY_LOCKED)}). Not allowed.")
        mv = MOVE.match(seg)
        if not mv:
            continue
        verb = mv.group(1).lower()
        args = _args(mv.group(2))
        moving = verb in ("mv", "move", "ren", "rename", "move-item")
        if moving and any(PROTECTED.search(a) for a in (args[:-1] or args)):
            return "moving or renaming files out of a protected folder is not allowed."
        if args and LOCKED_DEST.search(args[-1]):
            return f"{', '.join(BODY_LOCKED)} is written by the parsers only (tools/ingest)."
        if args and not moving and PROTECTED.search(args[-1]):
            dest = relpath(args[-1]) or args[-1]
            if dest.startswith(IMMUTABLE) and dest not in IMMUTABLE_EXCEPT and (REPO / dest).is_file():
                return "copying over an existing file in an immutable folder is not allowed."
    return None


def main() -> int:
    call = read_call()
    if call is None:
        return 0
    if call.kind == "shell":
        reason = check_shell(call.command)
        return deny(call, reason) if reason else 0
    if call.kind in ("write", "patch"):
        for p in call.paths:
            r = relpath(p)
            if r is None:
                continue
            reason = check_path(call, r)
            if reason:
                return deny(call, reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
