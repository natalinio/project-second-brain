#!/usr/bin/env sh
# Create the project environment in ./.venv (inside this folder) and initialise the KB.
#   ./scripts/setup.sh              core dependencies
#   ./scripts/setup.sh docs ole     + optional extras (docs = document parsing)
set -e
cd "$(dirname "$0")/.."

command -v git >/dev/null 2>&1 || { echo "git not found: install it first (see PREREQUISITES.md)"; exit 1; }
command -v uv  >/dev/null 2>&1 || { echo "uv not found: install it first (see PREREQUISITES.md)"; exit 1; }

# Keep the environment in this folder, whatever the shell had configured.
unset VIRTUAL_ENV UV_PROJECT_ENVIRONMENT

extras=""
for e in "$@"; do extras="$extras --extra $e"; done
# shellcheck disable=SC2086
uv sync --extra dev $extras

[ -d .git ] || git init -q -b main
uv run python tools/kb/hooks/git_pre_commit.py --install
uv run python tools/kb/refresh.py
echo
echo "Ready. Environment: $(pwd)/.venv"
echo "Next: edit project.yaml, then run /init-brain in Claude Code or GitHub Copilot."
