@echo off
REM Launch the Gemini Poetry scanner using uv + .venv.
REM Usage: run.bat [--top 5] [--repos owner/repo,...] [--user username] [...]

setlocal
cd /d "%~dp0"

:: Ensure uv is available
where uv >nul 2>&1
if errorlevel 1 (
    echo uv is required but not installed. Install: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

:: Create the .venv with uv if missing
if not exist ".venv\pyvenv.cfg" (
    echo Creating .venv with uv...
    uv venv .venv
)

:: Sync dependencies with uv
uv pip install --python .venv -r requirements.txt --quiet

:: Activate venv and run
call ".venv\Scripts\activate.bat"
python scan_poems.py %*
endlocal
