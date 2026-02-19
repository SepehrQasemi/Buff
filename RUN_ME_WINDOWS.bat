@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%RUN_ME_WINDOWS.ps1" %*
exit /b %ERRORLEVEL%
