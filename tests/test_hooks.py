"""The write guard, fed the payloads of each supported agent."""

import json

from conftest import py

PRE = "tools/kb/hooks/pre_tool.py"
POST = "tools/kb/hooks/post_tool.py"


def claude(brain, tool, **tool_input):
    return py(brain, PRE, stdin=json.dumps({"tool_name": tool, "tool_input": tool_input}))


def copilot(brain, tool, args, as_string=False, script=PRE):
    payload = {"toolName": tool, "toolArgs": json.dumps(args) if as_string else args,
               "cwd": str(brain), "timestamp": 0}
    return py(brain, script, stdin=json.dumps(payload))


def denied(r) -> bool:
    """Denied in either dialect: exit 2 (Claude) or a JSON deny on stdout (Copilot)."""
    if r.returncode == 2:
        return True
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False
    return out.get("permissionDecision") == "deny"


def _extracted(brain):
    p = brain / "knowledge" / "extracted" / "specs" / "n.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: N\nstatus: extracted\n---\n\n# N\n\nbody text\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------- Claude Code


def test_claude_source_is_immutable(brain):
    r = claude(brain, "Write", file_path=str(brain / "source" / "specs" / "x.md"), content="x")
    assert r.returncode == 2 and "immutable" in r.stderr


def test_claude_manifest_is_writable(brain):
    assert claude(brain, "Write", file_path=str(brain / "source" / "MANIFEST.md"), content="x").returncode == 0


def test_claude_extracted_body_locked_frontmatter_open(brain):
    p = _extracted(brain)
    assert denied(claude(brain, "Edit", file_path=str(p), old_string="body text", new_string="changed"))
    r = claude(brain, "Edit", file_path=str(p), old_string="status: extracted", new_string="status: checked")
    assert r.returncode == 0


def test_claude_generated_register_view_blocked(brain):
    py(brain, "tools/kb/refresh.py")
    view = brain / "artifacts" / "registers" / "open_points.md"
    r = claude(brain, "Edit", file_path=str(view), old_string="Open", new_string="Closed")
    assert r.returncode == 2 and "generated" in r.stderr


def test_claude_shell_guard_posix_and_windows_paths(brain):
    assert denied(claude(brain, "Bash", command="rm -rf source/specs"))
    assert denied(claude(brain, "PowerShell", command=r"Remove-Item knowledge\extracted\specs\n.md"))
    assert denied(claude(brain, "Bash", command="echo hi > knowledge/extracted/specs/n.md"))
    assert denied(claude(brain, "Bash", command="mv source/specs/a.pdf inbox/"))
    # triage into source/ is the normal flow and must stay allowed
    assert claude(brain, "Bash", command='mv "inbox/new spec.pdf" source/specs/').returncode == 0
    assert claude(brain, "Bash", command="ls source/specs").returncode == 0


# ---------------------------------------------------------------- GitHub Copilot (VS Code agent)


def test_copilot_vscode_create_in_source_denied(brain):
    r = copilot(brain, "create_file", {"filePath": str(brain / "source" / "data" / "x.csv"), "content": "a"})
    assert denied(r) and r.returncode == 0          # JSON decision, not an error exit
    assert "immutable" in json.loads(r.stdout.strip().splitlines()[-1])["permissionDecisionReason"]


def test_copilot_vscode_replace_string(brain):
    p = _extracted(brain)
    assert denied(copilot(brain, "replace_string_in_file",
                          {"filePath": str(p), "oldString": "body text", "newString": "x"}))
    assert not denied(copilot(brain, "replace_string_in_file",
                              {"filePath": str(p), "oldString": "status: extracted", "newString": "status: checked"}))


def test_copilot_vscode_multi_replace(brain):
    p = _extracted(brain)
    args = {"replacements": [{"filePath": str(p), "oldString": "status: extracted", "newString": "status: checked"},
                             {"filePath": str(p), "oldString": "body text", "newString": "x"}]}
    assert denied(copilot(brain, "multi_replace_string_in_file", args))


def test_copilot_vscode_apply_patch(brain):
    _extracted(brain)
    patch = "*** Begin Patch\n*** Update File: knowledge/extracted/specs/n.md\n@@\n-body text\n+x\n*** End Patch"
    assert denied(copilot(brain, "apply_patch", {"input": patch}))
    ok = "*** Begin Patch\n*** Add File: knowledge/curated/new.md\n+hello\n*** End Patch"
    assert not denied(copilot(brain, "apply_patch", {"input": ok}))


def test_copilot_vscode_terminal(brain):
    assert denied(copilot(brain, "run_in_terminal", {"command": "Remove-Item -Recurse source\\specs"}))
    assert not denied(copilot(brain, "run_in_terminal", {"command": "uv run python tools/kb/refresh.py"}))


def test_copilot_read_tools_allowed(brain):
    p = _extracted(brain)
    assert not denied(copilot(brain, "read_file", {"filePath": str(p)}))


# ---------------------------------------------------------------- GitHub Copilot CLI (toolArgs as JSON string)


def test_copilot_cli_payloads(brain):
    p = _extracted(brain)
    assert denied(copilot(brain, "bash", {"command": "rm -rf source"}, as_string=True))
    assert denied(copilot(brain, "bash", {"command": f"rm -f '{brain.as_posix()}/source/specs/a.pdf'"}, as_string=True))
    assert not denied(copilot(brain, "bash", {"command": 'git commit -m "add source notes"'}, as_string=True))
    assert denied(copilot(brain, "edit", {"path": str(p), "old_str": "body text", "new_str": "x"}, as_string=True))
    assert denied(copilot(brain, "create", {"path": str(brain / "source" / "a.md"), "file_text": "x"}, as_string=True))
    assert not denied(copilot(brain, "view", {"path": str(p)}, as_string=True))


# ---------------------------------------------------------------- post-write lint feedback


def test_post_tool_reports_lint_errors_to_both_agents(brain):
    bad = brain / "knowledge" / "curated" / "bad.md"
    bad.write_text("---\ntitle: Bad\ntype: x\nstatus: draft\norigin: curated\nevidence: rumour\n"
                   "updated: 2026-01-01\n---\n\n# Bad\n", encoding="utf-8")
    r = py(brain, POST, stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(bad)}}))
    assert r.returncode == 2 and "evidence" in r.stderr
    r = copilot(brain, "create_file", {"filePath": str(bad), "content": ""}, script=POST)
    assert r.returncode == 0 and "evidence" in json.loads(r.stdout.strip().splitlines()[-1])["reason"]
