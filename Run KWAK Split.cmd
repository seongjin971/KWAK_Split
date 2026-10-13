@echo off
set "APP_DIR=%~dp0release\compact-fix29\KWAK Split"
if exist "%APP_DIR%\KWAK Split.exe" (
    start "" "%APP_DIR%\KWAK Split.exe"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_dev.ps1"
    if errorlevel 1 pause
)
