"""Version detection and comparison.

Two halves:
  1. The installed BIOS version, read straight from Windows via WMI/CIM.
  2. The latest available BIOS version, read from Framework's community forum,
     which is the only public, machine-readable signal (there is no update API,
     and the official KB page is JavaScript-rendered).

Both halves fail gracefully -- if either can't be determined the app degrades
to "open the official page for you" rather than guessing.
"""
import re
import os
import subprocess
import logging

import requests

log = logging.getLogger("fuc.checker")

UA = "FrameworkUpdateChecker/1.0 (personal update notifier)"
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Matches "BIOS 3.06 Release STABLE", "BIOS 4.01 Release BETA", etc.
_TITLE_RE = re.compile(r"BIOS\s+(\d+\.\d+)\s+Release\s+(STABLE|BETA)", re.IGNORECASE)
_VER_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

# Default tokens that must ALL appear in a thread title for it to count as
# this machine's BIOS. Keeps Laptop 13 / 7040-series threads from being
# mistaken for the Laptop 16 AMD Ryzen AI 300. Overridable via
# sources.model_match_tokens in config.json.
_DEFAULT_MODEL_TOKENS = ["laptop 16", "ai 300"]


def _normalize(text: str | None) -> str:
    """Lowercase, collapse whitespace, and treat 'AI300' and 'AI 300' the same."""
    return re.sub(r"\s+", " ", (text or "").lower()).replace("ai300", "ai 300")


def _matches_model(title: str, cfg: dict) -> bool:
    norm = _normalize(title)
    tokens = (cfg.get("sources", {}) or {}).get("model_match_tokens") or _DEFAULT_MODEL_TOKENS
    return all(_normalize(tok) in norm for tok in tokens)


def get_installed_bios_version() -> str | None:
    """Read SMBIOSBIOSVersion via PowerShell CIM. Returns e.g. '03.06' or None."""
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "(Get-CimInstance -ClassName Win32_BIOS).SMBIOSBIOSVersion",
            ],
            capture_output=True, text=True, timeout=25,
            creationflags=_CREATE_NO_WINDOW,
        )
        value = (result.stdout or "").strip()
        if value:
            log.debug("Installed BIOS version: %s", value)
            return value
        log.warning("BIOS version query returned nothing. stderr=%s", result.stderr.strip())
        return None
    except Exception as e:
        log.warning("Could not read installed BIOS version: %s", e)
        return None


def parse_version(text: str | None) -> tuple | None:
    """Pull a comparable (major, minor, patch) tuple out of any version-ish string."""
    if not text:
        return None
    m = _VER_RE.search(text)
    if not m:
        return None
    return tuple(int(x) for x in m.groups(default="0"))


def is_newer(latest_ver: str | None, installed_ver: str | None):
    """True if latest > installed. None if either side is unknown (don't guess)."""
    lv = parse_version(latest_ver)
    iv = parse_version(installed_ver)
    if lv is None or iv is None:
        return None
    return lv > iv


def fetch_latest_bios(cfg: dict) -> dict | None:
    """Return the newest matching BIOS release as
    {'version','channel','title','url'} or None if it can't be determined.

    Honors the include_beta setting: when False, beta threads are ignored.
    """
    sources = cfg.get("sources", {})
    url = sources.get("community_search_url")
    if not url:
        return None
    try:
        resp = requests.get(
            url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=25
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("Could not fetch latest version from forum: %s", e)
        return None

    include_beta = cfg.get("include_beta", False)
    base = sources.get("community_base", "https://community.frame.work")
    candidates = []
    for topic in data.get("topics", []):
        title = topic.get("title", "") or ""
        if not _matches_model(title, cfg):
            continue  # e.g. a Laptop 13 / 7040-series thread -- not this machine
        m = _TITLE_RE.search(title)
        if not m:
            continue
        version, channel = m.group(1), m.group(2).upper()
        if channel == "BETA" and not include_beta:
            continue
        slug, tid = topic.get("slug"), topic.get("id")
        link = f"{base}/t/{slug}/{tid}" if slug and tid else sources.get("kb_url", base)
        candidates.append(
            {"version": version, "channel": channel, "title": title, "url": link}
        )

    if not candidates:
        log.info("No BIOS release threads matched the search.")
        return None

    candidates.sort(key=lambda c: parse_version(c["version"]) or (0,), reverse=True)
    best = candidates[0]
    log.debug("Latest BIOS found: %s (%s)", best["version"], best["channel"])
    return best


# Matches "Driver Bundle v2.00 2026_06_04 Release STABLE" (date optional).
_DRIVER_RE = re.compile(
    r"Driver\s+Bundle\s+v?(\d+\.\d+)(?:\s+(\d{4}_\d{2}_\d{2}))?.*?Release\s+(STABLE|BETA)",
    re.IGNORECASE,
)


def _get_json(url: str, accept: str = "application/json"):
    resp = requests.get(url, headers={"User-Agent": UA, "Accept": accept}, timeout=25)
    resp.raise_for_status()
    return resp.json()


def fetch_latest_driver_bundle(cfg: dict) -> dict | None:
    """Newest Windows driver bundle from the forum, model-filtered, honoring
    include_beta. Returns {'version','date','channel','title','url'} or None.

    Note: there's no reliable way to read the *installed* bundle version on
    Windows, so this is used for 'a new bundle was published' notifications, not
    installed-vs-latest comparison.
    """
    sources = cfg.get("sources", {})
    url = sources.get("driver_search_url")
    if not url:
        return None
    try:
        data = _get_json(url)
    except Exception as e:
        log.warning("Could not fetch latest driver bundle: %s", e)
        return None

    include_beta = cfg.get("include_beta", False)
    base = sources.get("community_base", "https://community.frame.work")
    candidates = []
    for topic in data.get("topics", []):
        title = topic.get("title", "") or ""
        if not _matches_model(title, cfg):
            continue
        m = _DRIVER_RE.search(title)
        if not m:
            continue
        version, date, channel = m.group(1), m.group(2), m.group(3).upper()
        if channel == "BETA" and not include_beta:
            continue
        slug, tid = topic.get("slug"), topic.get("id")
        link = f"{base}/t/{slug}/{tid}" if slug and tid else sources.get("driver_bundle_url", base)
        candidates.append(
            {"version": version, "date": (date or "").replace("_", "-"),
             "channel": channel, "title": title, "url": link}
        )

    if not candidates:
        return None
    candidates.sort(
        key=lambda c: (parse_version(c["version"]) or (0,), c.get("date", "")), reverse=True
    )
    return candidates[0]


def fetch_latest_keyboard_fw(cfg: dict) -> dict | None:
    """Latest keyboard / input-module firmware from the GitHub releases API.

    Tries /releases/latest first (which excludes drafts and prereleases). If that
    comes back empty -- some repos never mark a 'latest' -- it falls back to the
    releases list and picks the newest non-draft (skipping prereleases unless
    include_beta). Returns {'version','title','url','published'} or None.
    """
    sources = cfg.get("sources", {})
    api = sources.get("keyboard_releases_api")
    if not api:
        return None
    include_beta = cfg.get("include_beta", False)
    fallback_url = sources.get("keyboard_releases_url")

    def _shape(rel):
        tag = rel.get("tag_name") or rel.get("name")
        if not tag:
            return None
        # Pick the Windows updater asset to download (prefer a windows .zip/.exe).
        dl = None
        assets = rel.get("assets") or []
        for a in assets:
            n = (a.get("name") or "").lower()
            if ("win" in n) and (n.endswith(".zip") or n.endswith(".exe")):
                dl = a.get("browser_download_url")
                break
        if not dl and assets:
            dl = assets[0].get("browser_download_url")
        return {
            "version": tag,
            "title": rel.get("name") or tag,
            "url": rel.get("html_url") or fallback_url,
            "published": (rel.get("published_at") or "")[:10],
            "download": dl,
        }

    # 1) /releases/latest
    try:
        data = _get_json(api, accept="application/vnd.github+json")
        shaped = _shape(data) if isinstance(data, dict) else None
        if shaped:
            return shaped
    except Exception as e:
        log.info("Keyboard /releases/latest unavailable (%s); trying releases list.", e)

    # 2) Fall back to the releases list (newest first), skip drafts/prereleases.
    list_api = api.rsplit("/latest", 1)[0] + "?per_page=10"
    try:
        rels = _get_json(list_api, accept="application/vnd.github+json")
    except Exception as e:
        log.warning("Could not fetch keyboard releases list: %s", e)
        return None
    if not isinstance(rels, list):
        return None
    for rel in rels:
        if rel.get("draft"):
            continue
        if rel.get("prerelease") and not include_beta:
            continue
        return _shape(rel)
    return None


# --- direct download resolution from a forum thread ----------------------

_DL_FRAMEWORK_RE = re.compile(r'https://downloads\.frame\.work/[^\s"\'<>]+?\.(?:exe|zip|msi)', re.I)
_DL_ANY_RE = re.compile(r'https://[^\s"\'<>]+?\.(?:exe|zip|msi)', re.I)
_SHA256_RE = re.compile(r'\b[A-Fa-f0-9]{64}\b')


def resolve_forum_download(thread_url: str):
    """Given a Framework community thread URL, return (download_url, sha256) for
    the installer linked in the first post, using Discourse's JSON API. Returns
    (None, None) if it can't be found, so the app falls back to opening the page.
    """
    if not thread_url:
        return None, None
    try:
        data = _get_json(thread_url.rstrip("/") + ".json")
        posts = (data.get("post_stream", {}) or {}).get("posts", []) or []
        html = posts[0].get("cooked", "") if posts else ""
    except Exception as e:
        log.warning("Could not read thread for download link (%s): %s", thread_url, e)
        return None, None
    if not html:
        return None, None
    m = _DL_FRAMEWORK_RE.search(html) or _DL_ANY_RE.search(html)
    url = m.group(0) if m else None
    sha = None
    if url:
        s = _SHA256_RE.search(html)
        sha = s.group(0) if s else None
    return url, sha
