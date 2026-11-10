# Read-only status report for a Claude Code / Cursor Agent handoff.
# Does not modify the working tree, execute builds or contact paid services.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is not installed or not on PATH.'
}

# Resolve the repository relative to this script, even if invoked from elsewhere.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path (Join-Path $repoRoot '.git'))) {
    throw 'The RewindBox Git checkout could not be found beside this script.'
}

Push-Location $repoRoot
try {
    Write-Output '=== RewindBox AI handoff: Git state (read-only) ==='
    Write-Output "Repository: $repoRoot"
    Write-Output "Branch: $(& git branch --show-current)"
    Write-Output "HEAD: $(& git rev-parse HEAD)"
    Write-Output '--- Changes (including untracked file names) ---'
    & git status --short
    Write-Output '--- Change summary (tracked files) ---'
    & git diff --stat
    & git diff --cached --stat
    Write-Output '--- Last three commits ---'
    & git log -3 --oneline
    Write-Output '--- Shared project contract ---'
    if (Test-Path 'docs/AI_TASK_BOARD.md') {
        Write-Output 'docs/AI_TASK_BOARD.md exists; read its shared rules and current task before editing.'
    } else {
        Write-Output 'Missing shared contract; verify the current task and Git state before editing.'
    }
} finally {
    Pop-Location
}
