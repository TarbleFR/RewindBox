# Read-only status report for a Claude Code / Cursor Agent handoff.
# Does not modify the working tree, execute builds or contact paid services.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is not installed or not on PATH.'
}

$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $repoRoot) {
    throw 'Run this command from inside the RewindBox repository.'
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
    Write-Output '--- Handoff document ---'
    if (Test-Path 'docs/AI_HANDOFF.md') {
        Write-Output 'docs/AI_HANDOFF.md exists; read it before editing.'
    } else {
        Write-Output 'Missing handoff document; do not assume previous chat context.'
    }
} finally {
    Pop-Location
}
