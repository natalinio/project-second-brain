---
name: init-brain
description: Initialise this second brain for a new project from project.yaml. Run once after creating the repository from the template.
argument-hint: "[--demo]"
disable-model-invocation: true
---
Arguments: $ARGUMENTS (the text typed after the command; usually empty).

1. Read `project.yaml`. If `project_name` is still `My Project` or `description` is empty, ask the user for the
   project name, a one-sentence description, the main domains (3–8 short slugs) and the owners/teams, write them
   into `project.yaml`, then continue.
2. If `.venv/` does not exist in the project folder, run the setup script for the platform
   (`./scripts/setup.ps1` on Windows, `./scripts/setup.sh` elsewhere) and stop if it fails.
3. Run `uv run python tools/kb/bootstrap.py` (add `--demo` only if the user asked for it). It writes the project
   name into AGENTS.md and the knowledge index, creates the `source/` lanes, initialises empty registers, installs
   the git pre-commit hook and runs `tools/kb/refresh.py`.
4. Ask which systems, parties and concepts recur in this project (or propose them from `project.yaml`) and add
   them to `tools/kb/entities.yaml` with their aliases; run `uv run python tools/kb/refresh.py` again.
5. Reply in ≤ 8 lines: what was set up, and the next step ("drop material in `inbox/`, then `/ingest all`").
