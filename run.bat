@echo off
REM Run script for Gemini Code Assist PR Poetry Collection
REM This script runs the main collection program and then cleans up the poems

echo === Gemini Code Assist PR Poetry Collection ===
echo Starting collection process...

REM Run the main collection script
python get_new_flowers.py %*
if %ERRORLEVEL% neq 0 (
    echo Error: Collection process failed with exit code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo Collection process completed successfully.
echo Running cleanup process...

REM Run the cleanup script
python cleanup_poems.py
if %ERRORLEVEL% neq 0 (
    echo Error: Cleanup process failed with exit code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo Cleanup process completed successfully.
echo === All processes completed ===
