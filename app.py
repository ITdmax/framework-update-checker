"""Framework Update Checker - tray app and scheduler.

Checks Framework DIRECTLY on a schedule (their community forum for the BIOS and
the Windows driver bundle; their QMK GitHub for keyboard firmware), AUTO-DOWNLOADS
the installer from Framework's own CDN when something new is out, verifies it, and
notifies you so you can install now or later. It never flashes firmware silently --
you run the downloaded installer yourself.

Launch by double-clicking "Framework Update Checker.pyw" (no console window), or
run `pythonw app.py`. See README.md.
"""
import os
import sys
import threading
import logging
import subprocess
from datetime import datetime

import pystray
from PIL import Image, ImageDraw

import config
import checker
import notifier
import installer
import settings_gui  # bundled so the packaged exe can run --settings mode

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

APP_SCRIPT = os.path.abspath(__file__)
APP_DIR = os.path.dirname(APP_SCRIPT)


def _resource(name: str) -> str:
    """Locate a bundled data file, whether running from source or a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", APP_DIR)
    return os.path.join(base, name)

# --- logging -------------------------------------------------------------
LOG_DIR = config.config_dir()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "checker.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("fuc.app")

KINDS = ("BIOS", "Driver bundle", "Keyboard firmware")


def _make_icon_image() -> Image.Image:
    # Prefer the bundled icon.ico (proper "F"); fall back to a drawn square.
    try:
        p = _resource("icon.ico")
        if os.path.exists(p):
            return Image.open(p)
    except Exception:
        pass
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(33, 37, 41, 255))
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arialbd.ttf", 40)
        d.text((20, 6), "F", fill=(255, 255, 255, 255), font=font)
    except Exception:
        d.text((24, 20), "F", fill=(255, 255, 255, 255))
    return img


def _now():
    return datetime.now().isoformat(timespec="seconds")


# Win32 mouse-up message codes (stable across Windows versions).
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONUP = 0x0205


def _build_icon(title, image, menu):
    """Create the tray icon. On Windows, subclass so a LEFT click opens the
    context menu too -- pystray normally opens it only on right click."""
    if os.name == "nt" and hasattr(pystray.Icon, "_on_notify"):
        class _ClickableIcon(pystray.Icon):
            def _on_notify(self, wparam, lparam):
                # Remap left-button-up to right-button-up so either click pops
                # the menu (left-click otherwise just triggers the default item).
                if lparam == _WM_LBUTTONUP and getattr(self, "_menu_handle", None):
                    lparam = _WM_RBUTTONUP
                return super()._on_notify(wparam, lparam)
        return _ClickableIcon("framework_update_checker", image, title, menu=menu)
    return pystray.Icon("framework_update_checker", image, title, menu=menu)



class App:
    def __init__(self):
        self.cfg = config.load()
        # ready[kind] is None, or a dict with version/url/ident and (once
        # downloaded) 'file' = the local installer path on disk.
        self.ready = {k: None for k in KINDS}
        self.app_update = None       # newer version of THIS app, or None
        self.last_status = "starting up"
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.icon = _build_icon("Framework Update Checker",
                                _make_icon_image(), self._build_menu())

    # --- state helpers ---------------------------------------------------
    def _set_state(self, **kwargs):
        self.cfg.setdefault("state", {}).update(kwargs)
        config.save(self.cfg)

    def _reload_config(self):
        self.cfg = config.load()
        self.icon.update_menu()

    def _watching(self, kind):
        return {"BIOS": "watch_bios", "Driver bundle": "watch_drivers",
                "Keyboard firmware": "watch_keyboard"}.get(kind)

    def _unacted(self, kind, ident):
        """True if the user hasn't yet clicked Install for this exact version."""
        return bool(ident) and ident != self.cfg["state"].get("actioned", {}).get(kind, "")

    def _pending_count(self):
        return sum(1 for k, r in self.ready.items()
                   if r and r.get("file") and self._unacted(k, r.get("ident", "")))

    # --- menu ------------------------------------------------------------
    def _build_menu(self):
        def status_text(_i):
            return f"Status: {self.last_status}"

        def make_install_item(kind):
            def text(_i):
                r = self.ready.get(kind)
                if r and r.get("file"):
                    return f"Install {kind} {r['version']} now"
                if r:
                    return f"{kind} {r['version']} - open page"
                return f"{kind}: up to date"

            def visible(_i):
                return self.cfg.get(self._watching(kind), True)

            return pystray.MenuItem(text, lambda _ic=None, _it=None: self._install(kind),
                                    visible=visible)

        def app_update_item():
            def text(_i):
                e = self.app_update
                if e and e.get("file") and getattr(sys, "frozen", False):
                    return f"Update app to {e['version']} now"
                if e:
                    return f"App update {e['version']} - open release"
                return "App is up to date"

            def visible(_i):
                return self.app_update is not None

            return pystray.MenuItem(
                text, lambda _ic=None, _it=None: self._install_app_update(), visible=visible)

        return pystray.Menu(
            pystray.MenuItem(lambda _i: f"Framework Update Checker v{config.APP_VERSION}",
                             None, enabled=False),
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check now", lambda _i=None, _it=None: self._wake.set()),
            make_install_item("BIOS"),
            make_install_item("Driver bundle"),
            make_install_item("Keyboard firmware"),
            app_update_item(),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Framework BIOS page", self._on_open_kb),
            pystray.MenuItem("Create desktop shortcut", self._on_make_shortcut),
            pystray.MenuItem("Settings...", self._on_settings),
            pystray.MenuItem("Pause checks", self._on_toggle_pause,
                             checked=lambda _i: self.cfg["state"].get("paused", False)),
            pystray.MenuItem("Run at startup", self._on_toggle_startup,
                             checked=lambda _i: installer.is_run_at_startup()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    # --- menu actions ----------------------------------------------------
    def _on_open_kb(self, _i=None, _it=None):
        installer.open_url(self.cfg["sources"].get("kb_url"))

    def _on_make_shortcut(self, _i=None, _it=None):
        ok = installer.make_desktop_shortcut(APP_SCRIPT)
        notifier.notify("Framework Update Checker",
                        "Desktop shortcut created." if ok
                        else "Couldn't create the shortcut (see checker.log).")

    def _install(self, kind):
        r = self.ready.get(kind)
        if not r:
            return
        actioned = dict(self.cfg["state"].get("actioned", {}))
        actioned[kind] = r.get("ident", r.get("version", ""))
        self._set_state(actioned=actioned)
        f = r.get("file")
        if not (f and os.path.exists(f)):
            installer.open_url(r.get("url"))
        elif kind == "Keyboard firmware" and f.lower().endswith(".zip"):
            # Run only the flashers for the modules the user selected in Settings.
            installer.run_keyboard_flashers(f, self.cfg.get("keyboard_modules", []))
        else:
            installer.run_installer(f)
        self.icon.update_menu()

    def _install_app_update(self):
        e = self.app_update
        if not e:
            return
        actioned = dict(self.cfg["state"].get("actioned", {}))
        actioned["app"] = e["version"]
        self._set_state(actioned=actioned)
        f = e.get("file")
        if f and os.path.exists(f) and getattr(sys, "frozen", False):
            # Silent in-place update: the installer closes us, replaces files,
            # and relaunches (configured in installer.iss).
            installer.run_app_update(f)
        else:
            installer.open_url(e.get("url"))
        self.icon.update_menu()

    def _on_settings(self, _i=None, _it=None):
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--settings"]
        else:
            cmd = [sys.executable, os.path.join(APP_DIR, "settings_gui.py")]

        def run_and_reload():
            try:
                subprocess.run(cmd, timeout=600, creationflags=_CREATE_NO_WINDOW)
            except Exception as e:
                log.warning("Settings window error: %s", e)
            self._reload_config()

        threading.Thread(target=run_and_reload, daemon=True).start()

    def _on_toggle_pause(self, _i=None, _it=None):
        paused = not self.cfg["state"].get("paused", False)
        self._set_state(paused=paused)
        self.last_status = "paused" if paused else "running"
        self.icon.update_menu()

    def _on_toggle_startup(self, _i=None, _it=None):
        installer.set_run_at_startup(not installer.is_run_at_startup(), APP_SCRIPT)
        self.icon.update_menu()

    def _on_quit(self, _i=None, _it=None):
        self._stop.set()
        self._wake.set()
        self.icon.stop()

    # --- core check ------------------------------------------------------
    def check_once(self, manual=False):
        self._set_state(last_check_iso=_now())
        if self.cfg.get("watch_bios", True):
            self._check_bios(manual)
        if self.cfg.get("watch_drivers", True):
            self._check_drivers(manual)
        if self.cfg.get("watch_keyboard", True):
            self._check_keyboard(manual)
        try:
            self._check_app_update(manual)
        except Exception as e:
            log.warning("App update check error: %s", e)
        n = self._pending_count()
        self.last_status = (f"{n} update(s) downloaded, ready to install" if n
                            else "up to date")
        self.icon.update_menu()

    def _obtain(self, kind, latest, ident, download_url, sha=None):
        """Record the latest update and, if auto-download is on and we don't
        already have the file, download the installer from Framework."""
        entry = dict(latest)
        entry["ident"] = ident
        local = None
        if download_url:
            expected = installer.expected_path(download_url)
            if os.path.exists(expected):
                local = expected
            elif self.cfg.get("auto_download", True):
                local = installer.download(download_url, sha)
        entry["file"] = local
        self.ready[kind] = entry

    def _announce(self, kind, entry):
        v = entry["version"]
        f = entry.get("file")
        if f:
            uri = installer.file_uri(f)
            actions = []
            if uri:
                actions.append(("Install now", uri))
            if entry.get("url"):
                actions.append(("Release notes", entry["url"]))
            notifier.notify(
                f"{kind} {v} ready to install",
                "Downloaded from Framework. Click Install now, or use the tray icon later.",
                launch=uri or entry.get("url"),
                actions=actions,
            )
        else:
            notifier.notify(
                f"{kind} {v} available",
                "Couldn't auto-download it - click to open Framework's page.",
                url=entry.get("url"), button_label="Open page",
            )

    def _check_bios(self, manual):
        cfg = self.cfg
        installed = checker.get_installed_bios_version()
        if installed:
            self._set_state(installed_version_cache=installed)
        latest = checker.fetch_latest_bios(cfg)
        if latest is None:
            self.last_status = "couldn't reach BIOS source"
            if manual:
                notifier.notify("Framework Update Checker",
                                "Couldn't reach the BIOS source. Opening Framework's page.",
                                url=cfg["sources"].get("kb_url"), button_label="Open page")
            return
        result = checker.is_newer(latest["version"], installed)
        if result is True:
            url, sha = checker.resolve_forum_download(latest["url"])
            self._obtain("BIOS", latest, latest["version"], url, sha)
            if manual or self._unacted("BIOS", latest["version"]):
                self._announce("BIOS", self.ready["BIOS"])
        else:
            self.ready["BIOS"] = None
            if manual and result is False and cfg.get("notify_when_up_to_date", False):
                notifier.notify("Framework Update Checker", f"BIOS is up to date ({installed}).")

    def _check_drivers(self, manual):
        cfg = self.cfg
        latest = checker.fetch_latest_driver_bundle(cfg)
        if not latest:
            return
        ident = "{} {}".format(latest["version"], latest.get("date", "")).strip()
        url, sha = checker.resolve_forum_download(latest["url"])
        self._obtain("Driver bundle", latest, ident, url, sha)
        if manual or self._unacted("Driver bundle", ident):
            self._announce("Driver bundle", self.ready["Driver bundle"])

    def _check_keyboard(self, manual):
        cfg = self.cfg
        latest = checker.fetch_latest_keyboard_fw(cfg)
        if not latest:
            return
        ident = latest["version"]
        self._obtain("Keyboard firmware", latest, ident, latest.get("download"))
        if manual or self._unacted("Keyboard firmware", ident):
            self._announce("Keyboard firmware", self.ready["Keyboard firmware"])

    # --- app self-update -------------------------------------------------
    def _check_app_update(self, manual):
        cfg = self.cfg
        if not cfg.get("auto_update", True) or not cfg.get("app_repo", "").strip():
            self.app_update = None
            return
        latest = checker.fetch_latest_app_release(cfg["app_repo"])
        if not latest:
            return
        tag = latest["version"]
        if checker.is_newer(tag, config.APP_VERSION) is not True:
            self.app_update = None
            return
        local = None
        dl = latest.get("download")
        if dl:
            expected = installer.expected_path(dl)
            if os.path.exists(expected):
                local = expected
            elif cfg.get("auto_download", True):
                local = installer.download(dl)
        self.app_update = {"version": tag, "url": latest.get("url"), "file": local}
        # Fully unattended update (opt-in), exe build only.
        if (local and cfg.get("auto_install_app_updates", False)
                and getattr(sys, "frozen", False)):
            log.info("Auto-installing app update %s", tag)
            installer.run_app_update(local)
            return
        if manual or self._unacted("app", tag):
            self._announce_app(self.app_update)

    def _announce_app(self, entry):
        v = entry["version"]
        f = entry.get("file")
        if f and getattr(sys, "frozen", False):
            uri = installer.file_uri(f)
            actions = [("Update now", uri)] if uri else []
            if entry.get("url"):
                actions.append(("Release notes", entry["url"]))
            notifier.notify(
                f"App update {v} ready",
                "A new version of Framework Update Checker is ready. Click Update now, or use the tray icon for a silent update.",
                launch=entry.get("url") or uri,
                actions=actions,
            )
        else:
            notifier.notify(
                f"App update {v} available",
                "A new version is on GitHub - click to open the release.",
                url=entry.get("url"), button_label="Open release",
            )

    # --- scheduler loop --------------------------------------------------
    def _loop(self):
        if self._wake.wait(timeout=8):
            self._wake.clear()
        while not self._stop.is_set():
            if not self.cfg["state"].get("paused", False):
                try:
                    self.check_once(manual=self._wake.is_set())
                except Exception as e:
                    log.exception("Check failed: %s", e)
                    self.last_status = "check failed (see log)"
            self._wake.clear()
            interval_s = max(1, int(self.cfg.get("check_interval_hours", 12))) * 3600
            self._wake.wait(timeout=interval_s)

    def _on_ready(self, icon):
        icon.visible = True
        self.last_status = "running"
        threading.Thread(target=self._loop, daemon=True).start()

    def run(self):
        log.info("Starting Framework Update Checker.")
        self.icon.run(setup=self._on_ready)


_MUTEX_HANDLE = None


def _claim_mutex():
    """Create a named mutex matching installer.iss AppMutex, so the installer
    can detect, close, and relaunch this app during a silent self-update."""
    global _MUTEX_HANDLE
    if os.name != "nt":
        return
    try:
        import ctypes
        _MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, False,
                                                            "FrameworkUpdateCheckerMutex")
    except Exception as e:
        log.debug("Could not create mutex: %s", e)


def main():
    if "--settings" in sys.argv:
        settings_gui.main()
    else:
        _claim_mutex()
        App().run()


if __name__ == "__main__":
    main()
