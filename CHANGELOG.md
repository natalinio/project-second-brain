# Changelog

## 0.1.0 — 2026-10-16

First public release: a domain-agnostic template for Claude Code and GitHub Copilot.

- Layered knowledge base: `inbox → source → knowledge (extracted | curated) → metadata → artifacts`.
- Rules as code: `tools/kb/schema.yaml`, lint, Claude Code PreToolUse/PostToolUse hooks, git pre-commit.
- YAML registers (open points, claims, decisions) with generated Markdown views and DuckDB tables.
- Deterministic knowledge graph (`graph.py about | impact | path | find`), declarative graph sources.
- Ingest pipeline: Docling documents, e-mail threads, embedded objects, spreadsheets/CSV to DuckDB, sample profiling.
- Slash commands as Agent Skills: `/ask`, `/ingest`, `/capture`, `/impact`, `/review-note`, `/kb-status`, `/init-brain`.
- Agent-neutral: one protocol (`AGENTS.md`), one skill set and one guard for Claude Code and GitHub Copilot (ADR-0003).
- Setup scripts (`scripts/setup.sh`, `scripts/setup.ps1`): environment in `./.venv` inside the project folder.
- Fictional demo project (`examples/demo/`), tests and CI.
