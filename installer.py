"""Download + launch helpers.

Downloads installers straight from Framework's CDN (verifying the SHA256 they
publish), launches them when the user clicks "Install now", and can create a
Desktop shortcut. It never flashes firmware itself -- the user runs the
downloaded installer / follows Framework's flashing steps.
"""
import os
import sys
import pathlib
import hashlib
import logging
import subprocess
import webbrowser

import requests

log = logging.getLogger("fuc.installer")

UA = "FrameworkUpdateChecker/1.0"
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def staging_dir() -> pathlib.Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    p = pathlib.Path(base) / "FrameworkUpdateChecker" / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def expected_path(url: str) -> str:
    """Where a given download URL's file would live locally."""
    name = (url or "").split("/")[-1].split("?")[0] or "framework_update_download"
    return str(staging_dir() / name)


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, expected_sha256: str | None = None) -> str | None:
    """Download to the staging dir (atomically), verifying SHA256 if provided.
    Returns the local path, or None on failure / checksum mismatch."""
    if not url:
        return None
    try:
        local = pathlib.Path(expected_path(url))
        tmp = local.with_name(local.name + ".part")
        with requests.get(url, stream=True, timeout=600, headers={"User-Agent": UA}) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        if expected_sha256:
            actual = sha256_of(tmp)
            if actual.lower() != expected_sha256.lower():
                log.warning("SHA256 mismatch for %s (got %s, expected %s)",
                            url, actual, expected_sha256)
                try:
                    tmp.unlink()
                except Exception:
                    pass
                return None
        os.replace(tmp, local)
        log.info("Downloaded %s", local)
        return str(local)
    except Exception as e:
        log.warning("Download failed for %s: %s", url, e)
        return None


def open_url(url: str) -> None:
    if not url:
        return
    try:
        if os.name == "nt":
            os.startfile(url)  # noqa: S606
        else:
            webbrowser.open(url)
    except Exception as e:
        log.warning("Could not open URL %s: %s", url, e)


def run_installer(path: str) -> bool:
    """Launch the downloaded installer (or open it in Explorer for zips)."""
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606
            return True
        log.info("(non-Windows) would launch: %s", path)
        return False
    except Exception as e:
        log.warning("Could not launch %s: %s", path, e)
        return False


# --- Desktop shortcut + run-at-startup (no .bat needed) ------------------

def _pythonw_target():
    """(target, args) for a shortcut. Uses pythonw.exe so no console appears."""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    exe = sys.executable
    pyw = exe if exe.lower().endswith("pythonw.exe") else exe.replace("python.exe", "pythonw.exe")
    return pyw, '"{}"'.format(os.path.abspath(os.path.join(os.path.dirname(__file__), "app.py")))


def _create_shortcut(lnk_path: str, app_script: str) -> bool:
    """Create a .lnk via PowerShell (called directly, so no cmd quoting issues)."""
    app_dir = os.path.dirname(os.path.abspath(app_script))
    target, args = _pythonw_target()
    icon = os.path.join(app_dir, "icon.ico")
    ico_line = "$s.IconLocation='{}';".format(icon) if os.path.exists(icon) else ""
    ps = (
        "$w=New-Object -ComObject WScript.Shell;"
        "$s=$w.CreateShortcut('{lnk}');"
        "$s.TargetPath='{t}';"
        "$s.Arguments='{a}';"
        "$s.WorkingDirectory='{wd}';"
        "{ico}"
        "$s.Save()"
    ).format(lnk=lnk_path, t=target, a=args, wd=app_dir, ico=ico_line)
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=30,
                       creationflags=_CREATE_NO_WINDOW)
        return os.path.exists(lnk_path)
    except Exception as e:
        log.warning("Shortcut creation failed: %s", e)
        return False


def make_desktop_shortcut(app_script: str) -> bool:
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        lnk = os.path.join(desktop, "Framework Update Checker.lnk")
        return _create_shortcut(lnk, app_script)
    except Exception as e:
        log.warning("Could not create desktop shortcut: %s", e)
        return False


def _startup_shortcut_path() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", "FrameworkUpdateChecker.lnk")


def is_run_at_startup() -> bool:
    try:
        return os.path.exists(_startup_shortcut_path())
    except Exception:
        return False


def set_run_at_startup(enable: bool, app_script: str) -> bool:
    lnk = _startup_shortcut_path()
    try:
        if not enable:
            if os.path.exists(lnk):
                os.remove(lnk)
            return True
        return _create_shortcut(lnk, app_script)
    except Exception as e:
        log.warning("Could not set run-at-startup=%s: %s", enable, e)
        return False


def file_uri(path: str) -> str | None:
    """A file:/// URI for a local file, for use as a toast button target."""
    try:
        return pathlib.Path(path).resolve().as_uri()
    except Exception:
        return None


def run_app_update(setup_path: str) -> bool:
    """Update the app in place by running its downloaded installer silently.
    The installer (see installer.iss: CloseApplications/RestartApplications +
    AppMutex) closes this running app, replaces it, and relaunches it. Returns
    True if the installer was launched."""
    try:
        if os.name != "nt":
            log.info("(non-Windows) would run app updater: %s", setup_path)
            return False
        args = [setup_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]
        subprocess.Popen(args, creationflags=_CREATE_NO_WINDOW)
        return True
    except Exception as e:
        log.warning("Could not launch app updater: %s", e)
        return False


def run_keyboard_flashers(zip_path: str, modules) -> int:
    """Extract the keyboard firmware zip and launch the flasher .exe(s) matching
    the input modules the user has (e.g. ['ansi','numpad']). If none are selected
    or matched, open the extracted folder so they can choose. Returns how many
    flashers were launched."""
    import zipfile
    import re
    try:
        zp = pathlib.Path(zip_path)
        dest = zp.parent / (zp.stem + "_fw")
        if not dest.exists():
            with zipfile.ZipFile(zp) as z:
                z.extractall(dest)
        exes = list(dest.rglob("*.exe"))
        tokens = [str(m).lower() for m in (modules or [])]
        ran = 0
        for token in tokens:
            for p in exes:
                parts = re.split(r"[^a-z0-9]+", p.name.lower())
                if token in parts:
                    try:
                        if os.name == "nt":
                            os.startfile(str(p))  # noqa: S606
                        ran += 1
                    except Exception as e:
                        log.warning("Flasher launch failed (%s): %s", p.name, e)
                    break
        if ran == 0 and os.name == "nt":
            os.startfile(str(dest))  # nothing selected/matched -> let them pick
        log.info("Keyboard flashers launched: %d (modules=%s)", ran, tokens)
        return ran
    except Exception as e:
        log.warning("Keyboard flashers failed: %s", e)
        try:
            if os.name == "nt":
                os.startfile(zip_path)  # noqa: S606
        except Exception:
            pass
        return 0
