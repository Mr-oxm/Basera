@echo off
setlocal enabledelayedexpansion

:: Navigate to the directory of this script
cd /d "%~dp0"

echo ===================================================
echo               Launching Basera Photo Editor
echo ===================================================
echo.

:: 1. Git pull
echo [1/3] Checking for updates (git pull)...
git pull
if errorlevel 1 (
    echo [WARNING] Git pull encountered an issue or offline. Continuing with local code...
)
echo.

:: 2. Check uv and sync dependencies
echo [2/3] Syncing dependencies (uv sync)...
where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 'uv' was not found in PATH!
    echo Please install uv from: https://docs.astral.sh/uv/
    echo Or run: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b 1
)

uv sync
if errorlevel 1 (
    echo [ERROR] 'uv sync' failed!
    pause
    exit /b 1
)
echo.

:: 3. Run Basera Photo Editor
echo [3/3] Starting Basera Photo Editor...
echo.
uv run python -m photo_editor %*
if errorlevel 1 (
    echo.
    echo [INFO] Application exited with code %errorlevel%.
    pause
)
