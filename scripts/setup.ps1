# Create the project environment in .\.venv (inside this folder) and initialise the KB.
#   .\scripts\setup.ps1                  core dependencies
#   .\scripts\setup.ps1 -Extras docs,ole + optional extras (docs = document parsing)
param([string[]]$Extras = @())
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

foreach ($tool in 'git', 'uv') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool not found: install it first (see PREREQUISITES.md)"
    }
}

# Keep the environment in this folder, whatever the shell had configured.
Remove-Item Env:VIRTUAL_ENV, Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue

$uvArgs = @('sync', '--extra', 'dev')
foreach ($e in $Extras) { $uvArgs += @('--extra', $e) }
& uv @uvArgs
if ($LASTEXITCODE) { exit $LASTEXITCODE }

if (-not (Test-Path .git)) { git init -q -b main }
& uv run python tools/kb/hooks/git_pre_commit.py --install
& uv run python tools/kb/refresh.py
Write-Host ""
Write-Host "Ready. Environment: $((Get-Location).Path)\.venv"
Write-Host "Next: edit project.yaml, then run /init-brain in Claude Code or GitHub Copilot."
