# run_scraper.ps1 — runs the price scraper then commits & pushes to GitHub
# Called by Windows Task Scheduler daily at 03:00

# Force UTF-8 output so the log is readable in any text editor
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

$project = $PSScriptRoot
$python  = "$project\.venv\Scripts\python.exe"
$log     = "$project\scraper_run.log"

function Write-Log($msg) {
    [System.IO.File]::AppendAllText($log, "$msg`n", $utf8NoBom)
}

# Rotate log: keep last 500 lines to avoid unbounded growth
if (Test-Path $log) {
    $lines = [System.IO.File]::ReadAllLines($log, $utf8NoBom)
    if ($lines.Count -gt 500) {
        [System.IO.File]::WriteAllLines($log, ($lines | Select-Object -Last 500), $utf8NoBom)
    }
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Log "`n=== Run started $timestamp ==="

# --- Step 1: run scraper ---
# -u = unbuffered stdout so output appears in the log in real-time
$env:PYTHONUNBUFFERED = "1"
& $python -u "$project\scraper\cardmarket_scraper.py" 2>&1 | ForEach-Object {
    [System.IO.File]::AppendAllText($log, "$_`n", $utf8NoBom)
    Write-Host $_
}

if ($LASTEXITCODE -ne 0) {
    Write-Log "! Scraper exited with code $LASTEXITCODE — skipping git push"
    exit $LASTEXITCODE
}

# --- Step 2: commit & push if products.json changed ---
Set-Location $project

$changed = git status --porcelain data/products.json
if ($changed) {
    $msg = "chore: auto-update prices $(Get-Date -Format 'yyyy-MM-dd HH:mm') (local)"
    git add data/products.json 2>&1 | ForEach-Object { [System.IO.File]::AppendAllText($log, "$_`n", $utf8NoBom) }
    git commit -m $msg      2>&1 | ForEach-Object { [System.IO.File]::AppendAllText($log, "$_`n", $utf8NoBom) }
    git push                2>&1 | ForEach-Object { [System.IO.File]::AppendAllText($log, "$_`n", $utf8NoBom) }
    Write-Log "✓ Committed and pushed: $msg"
} else {
    Write-Log "~ No price changes detected, nothing to push"
}

Write-Log "=== Run finished $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
