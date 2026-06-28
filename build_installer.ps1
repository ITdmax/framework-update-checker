# build_installer.ps1
# Turns the source into a double-click Windows installer.
#
# One-time prerequisite: Python 3.10+  (winget install Python.Python.3.13)
# Inno Setup is installed automatically via winget if it's missing.
#
# Easiest: just double-click "Build Installer.bat" instead of running this directly.
# Result: dist_installer\FrameworkUpdateCheckerSetup.exe

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# Find a working Python. The 'py' launcher dodges the Microsoft Store alias stub.
function Resolve-Python {
    foreach ($cmd in @("py", "python")) {
        try {
            $v = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3") { return $cmd }
        } catch {}
    }
    throw "Python 3 not found. Install it with:  winget install Python.Python.3.13   then re-run."
}
$py = Resolve-Python
Write-Host "Using Python launcher: $py" -ForegroundColor DarkCyan

Write-Host "[1/4] Cleaning previous build output..." -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist, dist_installer -ErrorAction SilentlyContinue

Write-Host "[2/4] Installing Python dependencies + PyInstaller..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip | Out-Host
& $py -m pip install -r requirements.txt pyinstaller | Out-Host

Write-Host "[3/4] Building the app with PyInstaller (windowed, one folder)..." -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name FrameworkUpdateChecker --icon icon.ico `
    --add-data "icon.ico;." `
    --collect-submodules pystray `
    --collect-all winotify `
    app.py
if (-not (Test-Path "dist\FrameworkUpdateChecker\FrameworkUpdateChecker.exe")) {
    throw "PyInstaller did not produce the expected exe. Check the output above."
}

Write-Host "[4/4] Compiling the installer with Inno Setup..." -ForegroundColor Cyan
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "Inno Setup not found - installing it via winget (one time)..." -ForegroundColor Yellow
    try {
        winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements | Out-Host
    } catch {
        Write-Host "winget could not install Inno Setup automatically." -ForegroundColor Yellow
    }
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) {
    throw "Inno Setup 6 (ISCC.exe) still not found. Install it from https://jrsoftware.org/isdl.php and re-run."
}
& $iscc installer.iss | Out-Host

$out = Join-Path $PSScriptRoot "dist_installer\FrameworkUpdateCheckerSetup.exe"
if (Test-Path $out) {
    Write-Host "`nDone! Your installer is ready:" -ForegroundColor Green
    Write-Host "  $out" -ForegroundColor Green
    Write-Host "Double-click it to install (it creates a Desktop icon)." -ForegroundColor Green
} else {
    throw "Inno Setup finished but the installer was not found where expected."
}
