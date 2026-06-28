@echo off
setlocal
REM Builds FrameworkUpdateCheckerSetup.exe. Requires Python (one-time:
REM winget install Python.Python.3.13). Inno Setup installs automatically if missing.
set "HERE=%~dp0"
set "SCRIPT=%HERE%build_installer.ps1"
if not exist "%SCRIPT%" (
    echo.
    echo ERROR: build_installer.ps1 was not found next to this file.
    echo Looked in: %HERE%
    echo Run this .bat from INSIDE the extracted "framework-update-checker" folder,
    echo where build_installer.ps1 and app.py live.
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
echo.
echo If it succeeded, your installer is in the "dist_installer" folder.
pause
