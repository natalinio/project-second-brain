# Contributing

Thanks for improving the template. Keep it **domain-agnostic**: anything specific to one
project belongs in that project's fork, not here.

## Ground rules

- One concern per pull request; describe the problem before the change.
- Configuration over code: a new project-specific behaviour should be a key in
  `tools/kb/schema.yaml`, `graph_sources.yaml` or `entities.yaml`, not an `if` in Python.
- No real project material in issues, PRs, tests or examples. The demo project
  (`examples/demo/`) is fictional; keep it that way.
- Keep the tools dependency-light: the core runs on duckdb, pandas, pyyaml, openpyxl.
  Heavy dependencies go into an optional extra.
- Cross-platform: test on Windows and on macOS or Linux when you touch paths, hooks or
  shell commands.

## Before opening a PR

```bash
./scripts/setup.sh          # or .\scripts\setup.ps1
uv run pytest
uv run python tools/kb/refresh.py --check
```

If you change the contract (schema, folder layout, evidence levels), add an ADR under
`artifacts/adr/` explaining why, and update `README.md` and `AGENTS.md`.

## Agent neutrality

Everything must keep working with **both** Claude Code and GitHub Copilot (ADR-0003):

- the protocol lives in `AGENTS.md` only (`CLAUDE.md` just imports it);
- commands are skills in `.claude/skills/`, with no agent-specific frontmatter such as `model:`;
- a new hook goes into both `.claude/settings.json` and `.github/hooks/kb-guard.json`, and its
  script reads payloads through `tools/kb/hooks/agent_io.py`;
- `tests/test_hooks.py` covers each agent's payload shape; add a case for any new tool name.
