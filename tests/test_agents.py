"""The agent layer stays consistent: skills, hook configs, protocol files."""

import json
import re

from conftest import REPO

SKILLS = sorted((REPO / ".claude" / "skills").glob("*/SKILL.md"))


def frontmatter(text: str) -> dict:
    import yaml

    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "missing frontmatter"
    return yaml.safe_load(m.group(1))


def test_every_documented_command_is_a_skill():
    names = {p.parent.name for p in SKILLS}
    assert names >= {"ask", "ingest", "capture", "impact", "review-note", "kb-status", "init-brain"}


def test_skills_follow_the_shared_format():
    for p in SKILLS:
        fm = frontmatter(p.read_text(encoding="utf-8"))
        assert fm["name"] == p.parent.name, p
        assert re.fullmatch(r"[a-z0-9-]{1,64}", fm["name"]), p
        assert 20 < len(fm["description"]) <= 1024, p
        assert "model" not in fm, f"{p}: model ids differ between agents; leave the model to the session"


def test_hook_configs_point_to_existing_scripts():
    claude = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    copilot = json.loads((REPO / ".github" / "hooks" / "kb-guard.json").read_text(encoding="utf-8"))
    assert copilot["version"] == 1
    commands = [h["command"] for ev in claude["hooks"].values() for m in ev for h in m["hooks"]]
    commands += [h[k] for ev in copilot["hooks"].values() for h in ev for k in ("bash", "powershell")]
    for c in commands:
        script = re.search(r"(tools/kb/hooks/\w+\.py)", c).group(1)
        assert (REPO / script).exists(), c
        assert "Scripts/python.exe" not in c and "bin/python" not in c, "hooks must go through uv run"


def test_protocol_is_single_source():
    assert "@AGENTS.md" in (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert not (REPO / ".github" / "copilot-instructions.md").exists(), "one instruction file only"
    settings = json.loads((REPO / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert settings["chat.useAgentsMdFile"] is True and settings["chat.useHooks"] is True
    assert settings["chat.useClaudeHooks"] is False
