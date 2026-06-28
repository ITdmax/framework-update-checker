# Building the Windows installer

This turns the source into **`FrameworkUpdateCheckerSetup.exe`** — a normal
setup wizard that installs the app (per-user, no admin), adds a Start Menu
shortcut, optionally starts it at sign-in, and registers an uninstaller in
Add/Remove Programs.

The actual `.exe` has to be built **on Windows** (PyInstaller and Inno Setup
aren't cross-platform). Pick one of the two paths below.

## Option A — Build locally (double-click, no commands)

One-time prerequisite:
- **Python 3.10+** — easiest via `winget install Python.Python.3.13`, or
  python.org (tick *"Add Python to PATH"*).

**Inno Setup is installed automatically** (via winget) the first time you build,
so you don't need to grab it yourself.

Then just **double-click `build_installer.bat`**. It installs the Python deps,
runs PyInstaller, installs Inno Setup if needed, compiles the installer, and
leaves it at:
```
dist_installer\FrameworkUpdateCheckerSetup.exe
```
Double-click that to install. The wizard offers a **Desktop icon** and a
**start-at-sign-in** option, and registers an uninstaller — so afterward you
launch the app from a normal double-click icon, no Python folder in sight. (To
tweak the wizard — name, version, shortcuts — edit `installer.iss`.)

### Don't want to build anything? (quickest)
Double-click **`Setup.pyw`** once. It installs the dependencies, drops a
*Framework Update Checker* icon on your desktop, and starts the app. That gives
you the double-click experience immediately (as long as Python is installed) —
the full installer above just adds the Start Menu entry and uninstaller on top,
and works on machines with no Python at all.

## Option B — Build in the cloud (no local tools)

If you'd rather not install Python/Inno locally, the included GitHub Actions
workflow builds it for you on a Windows runner:

1. Push this folder to a GitHub repo:
   ```powershell
   gh repo create framework-update-checker --private --source=. --push
   ```
2. Open the repo's **Actions** tab → the "Build Windows Installer" run →
   download the **FrameworkUpdateCheckerSetup** artifact.
3. (Optional) Push a version tag to also get a GitHub Release with the installer
   attached:
   ```powershell
   git tag v1.0.0 ; git push --tags
   ```

## What the installer does

- Installs to `%LOCALAPPDATA%\Programs\Framework Update Checker` (no admin).
- Adds a Start Menu shortcut, and a Desktop icon if you tick that box.
- If you tick the checkbox, adds a sign-in startup shortcut (the same one the
  app's tray "Run at startup" toggle manages, so they stay in sync).
- Adds an uninstaller you can run from Add/Remove Programs.
- Your settings and logs stay in `%APPDATA%\FrameworkUpdateChecker\` and are left
  alone on uninstall (delete that folder manually if you want a clean wipe).

## A note on the SmartScreen warning

Because the installer isn't code-signed, the first time you run it Windows
SmartScreen may say *"Windows protected your PC."* That's expected for any
unsigned app — click **More info → Run anyway**. Removing that warning entirely
requires a paid code-signing certificate, which isn't worth it for a personal
tool. (If you ever do want it signed, the `.iss` has a `SignTool` hook Inno can
use.)

## Cutting a new release (so the in-app updater sees it)

The app compares its built-in version to the latest GitHub release tag. For an
update to be detected and offered, bump all three together:

1. `APP_VERSION` in **config.py** (e.g. `"1.0.1"`)
2. `MyAppVersion` in **installer.iss** (e.g. `1.0.1`)
3. The git tag you push: `v1.0.1`

Push the tag (`git tag v1.0.1 && git push origin v1.0.1`, or draft a release in
the GitHub UI). The workflow builds `FrameworkUpdateCheckerSetup.exe` and attaches
it to the release. Installed copies that have your repo set in Settings will then
see `v1.0.1 > 1.0.0`, download it, and offer **Update app now**.
