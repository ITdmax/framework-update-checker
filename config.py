"""Configuration handling for Framework Update Checker.

Settings live in %APPDATA%\\FrameworkUpdateChecker\\config.json so they
survive reboots and can be edited either through the Settings window or by
hand. Everything the checker needs is here; nothing is hard-coded in logic.
"""
import os
import json
import pathlib
import logging

log = logging.getLogger("fuc.config")

APP_NAME = "FrameworkUpdateChecker"

# Bump this when you cut a new release, and keep it in sync with MyAppVersion in
# installer.iss and the git tag you push (e.g. tag "v1.0.1" -> APP_VERSION "1.0.1").
APP_VERSION = "1.0.13"

# Automation levels (exposed in the Settings window):
#   "notify"                    -> only tell me; never download or install
#   "auto_drivers_confirm_bios" -> trigger driver/Windows Update scans automatically,
#                                  but always ask before touching the BIOS
#   "fully_automatic"           -> also auto-download a BIOS updater you've pointed
#                                  it at and launch it (only on AC power). Note: it
#                                  still hands off to Framework's official updater for
#                                  the actual flash -- see README for why.
AUTOMATION_LEVELS = ("notify", "auto_drivers_confirm_bios", "fully_automatic")

DEFAULTS = {
    "automation_level": "auto_drivers_confirm_bios",
    "check_interval_hours": 12,
    "include_beta": False,          # if True, beta BIOS releases count as "available"
    "watch_bios": True,
    "watch_drivers": True,
    "watch_keyboard": True,         # keyboard / input-module firmware (GitHub releases)
    # Which input modules you physically have, so the keyboard "Install" runs only
    # the matching flashers from the firmware zip. Tokens: ansi, iso, jis, numpad, macropad.
    "keyboard_modules": [],
    "auto_download": True,          # auto-download the installer when an update is found
    "require_ac_power": True,        # safety guard for any install action
    "min_battery_percent": 30,      # don't install below this even on battery
    "notify_when_up_to_date": False,  # if True, a manual "Check now" confirms even when nothing's new
    # --- self-update (the app updating itself from its own GitHub releases) ---
    # "owner/repo" of where THIS app is published, e.g. "jdoe/framework-update-checker".
    # Leave blank to disable self-update entirely.
    "app_repo": "ITdmax/framework-update-checker",
    "auto_update": True,            # check GitHub for a newer version of this app
    "auto_install_app_updates": False,  # if True, install app updates silently with no prompt
    # Not currently used: download links are read from Framework's Resources page
    # (or a verified forum release thread) automatically.
    "bios_download_url": "",
    "sources": {
        # Framework's official BIOS & drivers page for THIS model. It is plain,
        # server-rendered HTML listing every stable BIOS and the current driver
        # bundle with download links and SHA256s, so it is the primary source for
        # stable releases. (It does not list betas -- those come from the forum.)
        "resources_url": "https://resources.frame.work/downloads/laptop-16/amd-ryzen-ai-300-series/",
        "community_base": "https://community.frame.work",
        # Forum release threads are only trusted when posted by a member of this
        # forum group (Framework's own staff). Anyone can post in the Laptop 16
        # category, so a look-alike thread title alone is not enough.
        "trusted_forum_group": "Framework",
        # Discourse public search endpoint, filtered to this exact board's BIOS threads.
        # If Framework ever changes the thread naming, edit this in Settings.
        "community_search_url": (
            "https://community.frame.work/search.json?"
            "q=Framework%20Laptop%2016%20Ryzen%20AI300%20BIOS%20Release%20order%3Alatest"
        ),
        # Every token here must appear in a release thread's title for it to be
        # treated as THIS machine's BIOS. This is what keeps a Framework Laptop 13
        # (or 7040-series) release from being mistaken for the Laptop 16 AI 300.
        "model_match_tokens": ["laptop 16", "ai 300"],
        # Page opened by "Open Framework BIOS page" and when a check can't complete.
        # (The old knowledge-base article is now just a stub pointing here.)
        "kb_url": "https://resources.frame.work/downloads/laptop-16/amd-ryzen-ai-300-series/",
        "driver_bundle_url": "https://knowledgebase.frame.work/bios-and-drivers-downloads-rJ3PaCexh",
        # Driver bundles are posted on the forum with versions, like BIOS.
        "driver_search_url": (
            "https://community.frame.work/search.json?"
            "q=Framework%20Laptop%2016%20AI300%20Driver%20Bundle%20Release%20order%3Alatest"
        ),
        # Keyboard / input-module firmware ships via GitHub releases (QMK). The
        # /releases/latest endpoint excludes prereleases automatically.
        "keyboard_releases_api": "https://api.github.com/repos/FrameworkComputer/qmk_firmware/releases/latest",
        "keyboard_releases_url": "https://github.com/FrameworkComputer/qmk_firmware/releases",
        "keyboard_kb_url": "https://knowledgebase.frame.work/keyboard-firmware-update-framework-laptop-16-r1LayV4Age",
    },
    # Runtime state the app maintains itself; you normally don't edit these.
    "state": {
        "last_seen_version": "",
        "last_seen_driver": "",
        "last_seen_keyboard": "",
        "last_check_iso": "",
        "installed_version_cache": "",
        "paused": False,
        # version per update type the user has clicked "Install" / "Mark installed"
        # on, so the app stops reminding about it until a newer one appears.
        "actioned": {},
        # version per update type we've already shown a notification for, so we
        # notify once per new version instead of on every check.
        "announced": {},
    },
}


def config_dir() -> pathlib.Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    p = pathlib.Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> pathlib.Path:
    return config_dir() / "config.json"


# The `sources` block exactly as it shipped through v1.0.12. Those versions saved
# the whole block into config.json, which pinned these values and stopped any
# later fix to a URL from taking effect. On load, any saved source that still
# equals its old default is dropped so the current default applies; anything the
# user actually changed is kept.
_LEGACY_SOURCE_DEFAULTS = {
    "community_base": "https://community.frame.work",
    "community_search_url": (
        "https://community.frame.work/search.json?"
        "q=Framework%20Laptop%2016%20Ryzen%20AI300%20BIOS%20Release%20order%3Alatest"
    ),
    "model_match_tokens": ["laptop 16", "ai 300"],
    "kb_url": (
        "https://knowledgebase.frame.work/"
        "framework-laptop-16-bios-and-driver-releases-amd-ryzen-ai-300-series-SJ72iJntel"
    ),
    "driver_bundle_url": "https://knowledgebase.frame.work/bios-and-drivers-downloads-rJ3PaCexh",
    "driver_search_url": (
        "https://community.frame.work/search.json?"
        "q=Framework%20Laptop%2016%20AI300%20Driver%20Bundle%20Release%20order%3Alatest"
    ),
    "keyboard_releases_api": "https://api.github.com/repos/FrameworkComputer/qmk_firmware/releases/latest",
    "keyboard_releases_url": "https://github.com/FrameworkComputer/qmk_firmware/releases",
    "keyboard_kb_url": "https://knowledgebase.frame.work/keyboard-firmware-update-framework-laptop-16-r1LayV4Age",
}


def _drop_stale_sources(data: dict) -> None:
    """Remove saved source values that are just old defaults (see above)."""
    src = data.get("sources")
    if not isinstance(src, dict):
        return
    for key in list(src):
        if key in _LEGACY_SOURCE_DEFAULTS and src[key] == _LEGACY_SOURCE_DEFAULTS[key]:
            del src[key]


def _deep_merge(defaults: dict, data: dict) -> dict:
    """Merge user data over defaults, one level deep for nested dicts."""
    merged = dict(defaults)
    for key, default_val in defaults.items():
        if isinstance(default_val, dict):
            merged[key] = {**default_val, **(data.get(key) or {})}
        elif key in data:
            merged[key] = data[key]
    # keep any extra keys the user added
    for key, val in data.items():
        if key not in merged:
            merged[key] = val
    return merged


def load() -> dict:
    path = config_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # corrupt file -> fall back to defaults, don't crash
            log.warning("Could not read config (%s); using defaults.", e)
            data = {}
    if not isinstance(data, dict):
        data = {}
    _drop_stale_sources(data)
    return _deep_merge(DEFAULTS, data)


def save(cfg: dict) -> None:
    """Write the config. Only `sources` entries the user changed are saved, so
    new defaults shipped in a later version still take effect. Written to a temp
    file first, then swapped in, so a crash mid-write can't corrupt it."""
    out = dict(cfg)
    defaults = DEFAULTS["sources"]
    changed = {k: v for k, v in (cfg.get("sources") or {}).items()
               if k not in defaults or defaults[k] != v}
    if changed:
        out["sources"] = changed
    else:
        out.pop("sources", None)
    path = config_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:
        log.error("Could not save config: %s", e)
