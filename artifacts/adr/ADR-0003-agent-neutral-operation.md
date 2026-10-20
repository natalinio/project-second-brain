---
title: Agent-neutral operation — one protocol, one command set, one guard for Claude Code and GitHub Copilot
type: adr
status: accepted
domain: meta
updated: 2026-10-20
tags: [second-brain, agents, hooks, skills]
---

# ADR-0003 — Agent-neutral operation

## Context

Teams use different AI coding agents; the two most common are Claude Code and GitHub
Copilot (agent mode in VS Code, Copilot CLI, the Copilot coding agent). The knowledge base
must behave the same whichever agent is used: same rules, same commands, same guards.
Duplicating the protocol or the commands per agent would make them drift — the failure
ADR-0002 exists to prevent.

Both agents now read open, shared formats:

| Concern | Claude Code | GitHub Copilot |
|---|---|---|
| Always-on instructions | `CLAUDE.md` (supports `@file` imports) | `AGENTS.md` |
| Commands | Agent Skills in `.claude/skills/<name>/SKILL.md`, invoked as `/name` | Agent Skills, also read from `.claude/skills/`, invoked as `/name` |
| Guards | hooks in `.claude/settings.json` | hooks in `.github/hooks/*.json` |
| Tools | terminal + file tools | terminal + file tools (agent mode) |

## Decision

1. **One protocol:** `AGENTS.md` is the single source. `CLAUDE.md` only imports it
   (`@AGENTS.md`) and adds two Claude-specific lines.
2. **One command set:** the commands are Agent Skills in `.claude/skills/`; both agents
   expose them as slash commands. Skills that write (`/capture`, `/ingest`, `/init-brain`)
   set `disable-model-invocation: true` so they run only when the user asks.
3. **One guard:** `tools/kb/hooks/pre_tool.py` and `post_tool.py` serve both agents.
   `agent_io.py` normalises both payload formats (`tool_name`/`tool_input`,
   `toolName`/`toolArgs`) and the different tool and argument names, and answers in kind
   (exit code 2 and/or `permissionDecision: deny`). Claude Code runs them from
   `.claude/settings.json`, Copilot from `.github/hooks/kb-guard.json`. In VS Code,
   `.vscode/settings.json` turns off Copilot's reading of Claude-format hooks, so each guard
   runs once per agent.
4. **One environment:** `.venv/` in the project root, created by `scripts/setup.*`; every
   hook and command runs `uv run python …` from the root.
5. **The git pre-commit hook** (lint + register check) is the agent-independent backstop:
   it holds even for an agent or editor without hook support.

## Alternatives considered

| Option | Why not |
|---|---|
| Separate prompt files per agent (`.github/prompts/`) | Two copies of every command, guaranteed drift |
| `.github/copilot-instructions.md` next to `AGENTS.md` | VS Code recommends one instruction file; two would duplicate the protocol |
| MCP server as the common layer | Both agents already run the tools in a terminal; MCP adds a server to maintain (ADR-0001) |

## Consequences

- A change to the protocol, a command or a guard is made once and applies to both agents.
- Hook payload formats are owned by the agent vendors and can change; `tests/test_hooks.py`
  covers each known shape, and the git pre-commit hook remains the backstop.
- Organisation policies can disable hooks or skills in an agent; PREREQUISITES.md says what
  to check.
