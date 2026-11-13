# Framework Update Checker (Framework Laptop 16, AMD Ryzen AI 300 / Windows 11)

A small system-tray app that takes the "go check the website" chore off your
plate. It runs quietly in the background, checks for new BIOS releases on a
schedule, tells you when one's out, and can kick off driver/Windows Update
scans for you. The automation level is a setting you change inside the app, so
you can start cautious and loosen it later.

## What it actually does

It checks Framework **directly** (no Windows Update), and when something new is
out it **downloads the installer for you** and notifies you to install it:

- **BIOS** — reads your installed version from Windows (`Win32_BIOS`) and compares
  it to the latest Framework release for *this exact model* (Laptop 16 / AI 300).
- **Driver bundle** — watches Framework's Resources page and forum for new
  Windows driver bundles.
- **Keyboard / input-module firmware** — watches Framework's QMK GitHub releases.

When an update is found, it downloads the installer straight from Framework's CDN
(verifying the SHA256 they publish), then shows a toast: *"X is ready to install."*
The tray gets an **Install X now** item — it keeps reminding you on each check
until you click it, so you can install now or later. **You run the installer
yourself**; it never flashes firmware silently (that's how boards get bricked).

Toggle each update type, the check interval, and auto-download in **Settings**.

### Why it works this way (the honest part)

Framework has **no update API**. Stable BIOS and driver releases are read from
Framework's official [Resources page](https://resources.frame.work/downloads/laptop-16/amd-ryzen-ai-300-series/)
for this model, which lists each download with its SHA256. Beta releases (and a
backup for the Resources page) come from the community forum, but only from
release threads posted by Framework's own team, since anyone can post a thread
with a look-alike title. Installers are only ever downloaded from
`downloads.frame.work`. Keyboard firmware comes from Framework's GitHub releases.
If no source can be reached, the app opens the official page for you instead of
guessing, and the tray status says which check couldn't run. The driver and keyboard
checks flag *newly published* releases rather than comparing to what's installed
— there's no reliable way to read the installed driver-bundle or keyboard
firmware version on Windows, so the app tells you when something new is out and
links you to it.

**On firmware specifically:** the app downloads the installer for you, but you
run it. It never silently flashes the BIOS or keyboard in the background — an
interrupted background flash is how hardware gets bricked, so that step stays in
your hands. For the driver bundle, clicking "Install" runs Framework's installer;
for BIOS/keyboard it opens the downloaded file so you can follow Framework's flash
steps.

## Setup

### One-click install: double-click `Setup`
Double-click **`Setup.pyw`**. It installs the components the app needs, puts a
*Framework Update Checker* icon on your desktop, optionally starts it with
Windows, and launches it into your system tray. No commands, no batch files.

From then on, start it anytime by double-clicking **`Framework Update Checker.pyw`**
(or the desktop icon). It runs through `pyw.exe`, so there's no console window.

- **Start with Windows** can also be toggled later: right-click the tray icon →
  **Run at startup**.
- *(If double-clicking a `.pyw` opens an editor instead of running it, right-click
  it → Open with → Python.)*

This one-click setup assumes Python is installed (the `py` launcher). For a build
that needs **no Python at all**, see "build an installer" below.

### Settings
Right-click (or left-click) the tray icon → **Settings**. Toggle which updates to
watch (BIOS / drivers / keyboard), auto-download, the check interval, and beta vs
stable. Changes take effect on the next check — hit *Check now* to apply now.

### Updating the app itself
The app can update *itself* from its own GitHub releases instead of you
reinstalling. In **Settings**, set **GitHub repo (owner/name)** to where you
published it (e.g. `yourname/framework-update-checker`). Then on each check it
asks GitHub for a newer release, downloads the new `FrameworkUpdateCheckerSetup.exe`,
and notifies you — the tray shows **Update app to vX now**, which installs it
silently and relaunches (the installer is set to close and restart the running
app). Tick **Install app updates silently** for fully hands-off updates. This
applies to the installed `.exe` build; running from source just notifies and
links the release. Self-update stays off until you set the repo.

Config, logs, and downloaded installers live under:
`%APPDATA%\FrameworkUpdateChecker\` and `%LOCALAPPDATA%\FrameworkUpdateChecker\downloads\`

## Optional: build an installer (.exe setup wizard)

If you'd rather have a real installer — one that creates **Desktop and Start
Menu icons**, an optional start-at-sign-in checkbox, and an uninstaller in
Add/Remove Programs, exactly like any other Windows app — see
**BUILD_INSTALLER.md**. Short version: install Python + Inno Setup once, then
**double-click `build_installer.bat`** to produce
`dist_installer\FrameworkUpdateCheckerSetup.exe`. (Or push to GitHub and let the
included Actions workflow build it, no local tools needed.) Run that setup once
and you'll have a double-click Desktop icon with no Python folder in sight.

## Troubleshooting

- **Tray status says "couldn't check …"** — that part of the check couldn't reach
  its source (or, for "installed BIOS version", couldn't read it from Windows).
  Check your internet; details are in `checker.log`. The app still works as a
  scheduled reminder.
- **No BIOS version detected** — make sure PowerShell runs
  `(Get-CimInstance Win32_BIOS).SMBIOSBIOSVersion` without error.
- **Want beta releases counted?** — Settings → "Include beta releases".
- Everything is logged to `checker.log` if something looks off.

---
*Heads-up: this was written for your Windows 11 machine but assembled on a Linux
box, so the Windows-specific bits (toasts, WMI, tray) couldn't be test-run here.
Watch the first run and check `checker.log` — ping me if anything misbehaves and
I'll fix it.*
