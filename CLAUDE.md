# Claude Code entry point

The operating protocol of this repository is shared by every AI agent and lives in
[AGENTS.md](AGENTS.md). Claude Code loads it through the import below; edit AGENTS.md,
not this file.

@AGENTS.md

## Claude Code specifics

- Commands are the skills in `.claude/skills/` (`/ask`, `/ingest`, `/capture`, ...).
- Guards run from `.claude/settings.json` (the same scripts GitHub Copilot runs from
  `.github/hooks/`).
