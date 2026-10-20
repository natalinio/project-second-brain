"""Normalise hook payloads from different AI agents into one shape, and answer in kind.

Supported payloads (stdin JSON):
  * Claude Code, and VS Code Copilot reading Claude-format hooks:
        {"tool_name": "Edit", "tool_input": {"file_path": ..., "old_string": ...}}
  * GitHub Copilot (VS Code agent, Copilot CLI, coding agent; `.github/hooks/*.json`):
        {"toolName": "replace_string_in_file", "toolArgs": {"filePath": ..., "oldString": ...}}
    where toolArgs may also arrive as a JSON string.

Answers: a denial is written both ways — `hookSpecificOutput.permissionDecision` and a
top-level `permissionDecision` on stdout, the reason on stderr — and the exit code is 2
(blocking) for the Claude-style payload, 0 with the JSON decision for the Copilot one.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

SHELL_TOOL = re.compile(r"^(bash|powershell|pwsh|shell|sh|run_in_terminal|runinterminal|terminal|"
                        r"run_command|execute_command|copilot_runinterminal)$", re.I)
WRITE_TOOL = re.compile(r"(edit|write|create|replace|patch|insert|notebook|str_replace|file_text)", re.I)
READ_TOOL = re.compile(r"(read|view|list|search|find|get|fetch|grep|glob)", re.I)
PATH_KEYS = ("file_path", "filePath", "path", "notebook_path", "notebookPath", "target_file", "uri")
OLD_KEYS = ("old_string", "oldString", "old_str")


@dataclass
class Call:
    style: str                      # "claude" | "copilot"
    tool: str
    kind: str                       # "shell" | "write" | "patch" | "other"
    command: str = ""
    paths: list[str] = field(default_factory=list)
    olds: list[str] = field(default_factory=list)   # strings an edit replaces (frontmatter check)
    whole: bool = False             # rewrites the whole file (Write / create)


def _args(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {"command": raw}
    return raw if isinstance(raw, dict) else {}


def _patch_paths(text: str) -> list[str]:
    return re.findall(r"^\*\*\* (?:Update|Add|Delete) File:\s*(.+?)\s*$", text or "", re.M)


def read_call() -> Call | None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return None
    if "tool_name" in data or "tool_input" in data:
        style, tool, args = "claude", str(data.get("tool_name", "")), _args(data.get("tool_input"))
    else:
        style = "copilot"
        tool = str(data.get("toolName") or data.get("tool_name") or "")
        args = _args(data.get("toolArgs") if "toolArgs" in data else data.get("tool_input"))

    if SHELL_TOOL.match(tool) or (tool.lower().endswith("terminal")):
        return Call(style, tool, "shell", command=str(args.get("command", "")))
    if "patch" in tool.lower() and isinstance(args.get("input") or args.get("patch"), str):
        return Call(style, tool, "patch", paths=_patch_paths(args.get("input") or args.get("patch")))

    paths, olds = [], []
    for key in PATH_KEYS:
        if isinstance(args.get(key), str):
            paths.append(args[key])
    for key in OLD_KEYS:
        if key in args:
            olds.append(str(args[key]))
    for group in ("edits", "replacements"):
        for e in args.get(group) or []:
            if isinstance(e, dict):
                for key in PATH_KEYS:
                    if isinstance(e.get(key), str) and e[key] not in paths:
                        paths.append(e[key])
                for key in OLD_KEYS:
                    if key in e:
                        olds.append(str(e[key]))
    if not paths or (READ_TOOL.search(tool) and not WRITE_TOOL.search(tool)):
        return Call(style, tool, "other")
    whole = not olds and any(k in args for k in ("content", "file_text", "text")) \
        or tool in ("Write", "NotebookEdit") or "create" in tool.lower()
    return Call(style, tool, "write", paths=paths, olds=olds, whole=whole)


def deny(call: Call | None, reason: str) -> int:
    msg = f"KB contract: {reason}"
    print(json.dumps({
        "permissionDecision": "deny",
        "permissionDecisionReason": msg,
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                               "permissionDecisionReason": msg},
    }))
    print(msg, file=sys.stderr)
    return 0 if call is not None and call.style == "copilot" else 2


def feedback(call: Call | None, text: str) -> int:
    """PostToolUse: hand lint errors back to the agent so it fixes them."""
    print(json.dumps({
        "decision": "block",
        "reason": text,
        "additionalContext": text,
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text},
    }))
    print(text, file=sys.stderr)
    return 0 if call is not None and call.style == "copilot" else 2
