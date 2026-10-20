# Prerequisites

Everything to have in place before running `scripts/setup` and `/init-brain`. Tick the
checklist at the end.

## 1. Licences and accounts

You need **one** of the two agents; both work on the same repository.

| Item | Required | Notes |
|---|---|---|
| **Claude Code** access | One agent is required | A Claude subscription that includes Claude Code, or an API account with credits (API key). |
| **GitHub Copilot** access | One agent is required | A Copilot plan that includes **agent mode** in VS Code. In a managed organisation, the admin policy must allow agent mode, custom instructions (`AGENTS.md`), agent skills and **agent hooks**; see §5. |
| Git hosting account | Optional | Only to create the repository from the template on a Git host, or to push it there. Keep a real project's repository **private**. |
| **Approval to use AI on the material** | Yes, for any confidential material | Confirm with the data owner that the material may be processed by the agent you use. `source/` stays local and gitignored; the protocol forbids sending it to any other external service. |

## 2. Software

| Tool | Version | Why |
|---|---|---|
| **Git** | ≥ 2.40 | Version control and the pre-commit backstop (on Windows it also provides Git Bash) |
| **uv** | ≥ 0.5 | Creates `./.venv` in the project folder, installs the Python dependencies, runs every tool and hook (`uv run …`). Installation guide: <https://docs.astral.sh/uv/getting-started/installation/> |
| **Python** | ≥ 3.11 | The tools are Python. If no suitable interpreter is installed, uv downloads one automatically. |
| **Claude Code** *or* **VS Code + GitHub Copilot Chat** | current | The agent. Claude Code runs in a terminal or as a VS Code extension. Copilot runs in VS Code chat, in **Agent** mode. |
| Node.js | ≥ 18 | Only if you install Claude Code through npm |

`uv` must be on the `PATH` of the shell your agent uses: the hooks run `uv run …`.

## 3. The project environment (`.venv`)

The Python environment is created **inside the project folder**, at `./.venv/`, by the
setup script:

```bash
./scripts/setup.sh                 # macOS / Linux / Git Bash
.\scripts\setup.ps1                # Windows PowerShell
```

- Every dependency lives in `./.venv/` (gitignored), next to the project. Delete the
  folder and re-run the script to rebuild it. Only the base Python interpreter, when uv
  had to download one, sits in uv's own cache.
- The scripts unset `VIRTUAL_ENV` and `UV_PROJECT_ENVIRONMENT`, so a globally configured
  environment never takes over.
- `pyproject.toml` sets uv's `link-mode = "copy"`. That is slightly slower than
  hardlinks, but it also works when the project folder sits in a cloud-synced directory.
- VS Code picks `./.venv` automatically (`.vscode/settings.json`).

## 4. Python packages

Installed into `./.venv` from `pyproject.toml`:

| Group | Packages | When |
|---|---|---|
| core | `duckdb`, `pandas`, `tabulate`, `openpyxl`, `python-pptx`, `pyyaml` | Always: registers, graph, lint, SQL, e-mail, spreadsheets |
| `docs` extra | `docling` (pulls PyTorch; downloads layout and table-structure models on first run) | To parse PDF/DOCX/PPTX/HTML. Plan **2–4 GB of disk** and **8 GB RAM** (16 GB for large PDFs). |
| `ole` extra | `olefile` | To unwrap OLE-embedded objects (legacy `.xls`/`.doc` inside Office files) |
| `tls` extra | `truststore` | Behind a TLS-intercepting proxy (see §6) |
| `dev` extra | `pytest` | Tests; installed by the setup scripts |

```bash
./scripts/setup.sh docs ole        # or: .\scripts\setup.ps1 -Extras docs,ole
```

## 5. Agent configuration

**Claude Code.** Nothing to configure. It reads `CLAUDE.md` (which imports `AGENTS.md`),
the skills in `.claude/skills/` and the hooks in `.claude/settings.json`. Approve the
project hooks the first time Claude Code asks.

**GitHub Copilot (VS Code).** The repository ships `.vscode/settings.json` with:

| Setting | Value | Why |
|---|---|---|
| `chat.useAgentsMdFile` | `true` | Load `AGENTS.md` as always-on instructions |
| `chat.useHooks` | `true` | Run the guards in `.github/hooks/kb-guard.json` |
| `chat.useClaudeHooks` | `false` | Don't run the Claude-format copy too: each guard runs once |
| `chat.useClaudeMdFile` | `false` | `CLAUDE.md` only imports `AGENTS.md`, which is already loaded |
| `python.defaultInterpreterPath` | `${workspaceFolder}/.venv` | Use the project environment |

Then:
- open the folder and **trust the workspace** (hooks and skills from the repository load
  only in a trusted workspace);
- in Copilot Chat, select **Agent** mode;
- type `/` to check that `ask`, `ingest`, `capture`… are listed.

If your organisation's policy disables hooks, the commands still work. The git
pre-commit hook then remains the only automatic guard, so review agent edits before
committing.

## 6. Network and environment notes

- **TLS-intercepting proxy**: `uv sync` may need `--native-tls`. Docling's model download
  fails with `CERTIFICATE_VERIFY_FAILED` unless you install the `tls` extra and set
  `KB_USE_TRUSTSTORE=1` (or pass `--truststore` to `parse_docs.py`).
- **Blocked downloads**: DuckDB extensions are never needed (Excel is read through
  openpyxl). OCR is off by default; `--ocr` needs one more model download.
- **Cloud-synced project folder**: supported thanks to `link-mode = "copy"`. If the sync
  client locks files during an install, pause syncing and re-run the setup script.
- **Windows long paths**: deep `source/` trees can exceed 260 characters. Enable long
  paths (`git config --global core.longpaths true` and the Windows long-path policy), or
  keep the project folder near the drive root.

## 7. Checklist

- [ ] `git --version` ≥ 2.40
- [ ] `uv --version` works in the shell your agent uses
- [ ] Agent ready: `claude --version` (logged in), **or** VS Code with Copilot Chat signed in and Agent mode available
- [ ] Approval to process the project material with that agent
- [ ] Repository created from the template (**private** for real projects)
- [ ] `scripts/setup.sh` / `scripts/setup.ps1` completed → `./.venv/` exists in the project folder
- [ ] `uv run python tools/kb/refresh.py` → `0 error(s)`
- [ ] `project.yaml` filled in, then `/init-brain` run in the agent
