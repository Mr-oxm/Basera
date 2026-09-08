# Set project directory to script location
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "              Launching Basera Photo Editor        " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Git pull
Write-Host "[1/3] Checking for updates (git pull)..." -ForegroundColor Yellow
try {
    git pull
} catch {
    Write-Warning "Git pull encountered an issue. Continuing with local version..."
}
Write-Host ""

# 2. Check uv and sync dependencies
Write-Host "[2/3] Syncing dependencies (uv sync)..." -ForegroundColor Yellow
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 'uv' is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Install it with: powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Cyan
    Read-Host "Press Enter to exit"
    exit 1
}

uv sync
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 'uv sync' failed!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# 3. Run Basera Photo Editor
Write-Host "[3/3] Starting Basera Photo Editor..." -ForegroundColor Green
Write-Host ""

uv run python -m photo_editor @args
