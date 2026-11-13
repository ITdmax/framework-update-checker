"""Version detection and comparison.

Two halves:
  1. The installed BIOS version, read straight from Windows via WMI/CIM.
  2. The latest available BIOS / driver bundle. Framework has no update API, so
     this reads their official Resources page (stable releases, with download
     links and SHA256s) and their community forum (betas, and a backup source).
     Forum threads only count when posted by Framework's own team, and installers
     are only ever downloaded from downloads.frame.work.

Both halves fail gracefully -- if either can't be determined the app degrades
to "open the official page for you" rather than guessing.
"""
import re
import os
import time
import subprocess
import logging

import requests

log = logging.getLogger("fuc.checker")

UA = "FrameworkUpdateChecker/1.0 (personal update notifier)"
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

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


# --- shared helpers -------------------------------------------------------

def _get_json(url: str, accept: str = "application/json"):
    resp = requests.get(url, headers={"User-Agent": UA, "Accept": accept}, timeout=25)
    resp.raise_for_status()
    return resp.json()


def _get_text(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=25)
    resp.raise_for_status()
    return resp.text


# Installers are only ever downloaded from Framework's own CDN.
_DL_FRAMEWORK_RE = re.compile(r'https://downloads\.frame\.work/[^\s"\'<>]+?\.(?:exe|zip|msi)', re.I)
_SHA256_RE = re.compile(r'\b[A-Fa-f0-9]{64}\b')
# Framework marks withdrawn releases in the title, e.g. "... Release BETA (Held)".
_WITHDRAWN_RE = re.compile(r"\b(held|pulled|withdrawn)\b", re.IGNORECASE)


def _release_key(rel: dict) -> tuple:
    return (parse_version(rel.get("version")) or (0,), rel.get("date", ""))


def _pick_newer(official: dict | None, forum: dict | None) -> dict | None:
    """Pick the newer of a Resources-page release and a forum release. When both
    describe the same release, keep the Resources entry (filling in the download
    from the forum if needed) -- but if the two official sources disagree on the
    file's SHA256, don't auto-download it at all."""
    if not official or not forum:
        return official or forum
    ko, kf = _release_key(official), _release_key(forum)
    if kf > ko:
        return forum
    if ko > kf:
        return official
    merged = dict(official)
    so, sf = (official.get("sha") or "").lower(), (forum.get("sha") or "").lower()
    if so and sf and so != sf:
        log.warning("SHA256 for %s differs between the Resources page and the forum; "
                    "not auto-downloading it.", official.get("title"))
        merged["download"], merged["sha"] = None, None
    elif not merged.get("download") and forum.get("download"):
        merged["download"], merged["sha"] = forum["download"], forum.get("sha")
    return merged


# --- Framework Resources page (official, stable releases) -----------------
# resources.frame.work/downloads/<model>/ is plain server-rendered HTML. Each
# download is a table row: the downloads.frame.work link, its release date, the
# filename and "SHA256 · <hex>". Parsing keys off those links and the text right
# after each one, not CSS classes, so cosmetic redesigns don't break it.

_RES_LINK_RE = re.compile(
    r'href="(https://downloads\.frame\.work/(bios|driver)/([^"\s<>]+?\.exe))"', re.IGNORECASE)
_RES_SHA_RE = re.compile(r'SHA-?256(?:\W|&[#\w]+;){0,8}?([A-Fa-f0-9]{64})\b', re.IGNORECASE)
_RES_BADGE_RE = re.compile(r'>\s*(Stable|Beta)\s*<', re.IGNORECASE)
_RES_BIOS_VER_RE = re.compile(r'_BIOS_(\d+\.\d+)\.exe$', re.IGNORECASE)
_RES_DRV_LABEL_RE = re.compile(r'Driver\s+Bundle\s+v?(\d+\.\d+)', re.IGNORECASE)
_RES_DRV_FILE_RE = re.compile(r'_v(\d)(\d{2})_(\d{4})_(\d{2})_(\d{2})\.exe$', re.IGNORECASE)
_RES_DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')

_res_cache = {"url": None, "at": 0.0, "data": None}


def parse_resources_html(html: str, page_url: str) -> dict:
    """Pull every BIOS installer and driver bundle out of a Resources page.
    Returns {'bios': [newest first], 'driver': newest or None}."""
    base = page_url.rstrip("/")
    links = list(_RES_LINK_RE.finditer(html))
    bios, drivers = [], []
    prev_end = 0
    for i, m in enumerate(links):
        # Everything up to the next download link belongs to this row.
        row = html[m.end(): links[i + 1].start() if i + 1 < len(links) else len(html)]
        s = _RES_SHA_RE.search(row)
        sha = s.group(1) if s else None
        d = _RES_DATE_RE.search(row)
        row_date = "-".join(d.groups()) if d else ""
        dl, kind = m.group(1), m.group(2).lower()
        fname = m.group(3).rsplit("/", 1)[-1]
        if kind == "bios":
            v = _RES_BIOS_VER_RE.search(fname)
            if v:
                # The Stable/Beta badge sits at the top of this release's block.
                badges = _RES_BADGE_RE.findall(html, prev_end, m.start())
                ver = v.group(1)
                bios.append({
                    "version": ver, "channel": (badges[-1] if badges else "Stable").upper(),
                    "title": f"BIOS {ver}", "url": f"{base}/{ver}", "released": row_date,
                    "download": dl, "sha": sha, "source": "resources",
                })
        else:
            lab = _RES_DRV_LABEL_RE.search(row)
            f = _RES_DRV_FILE_RE.search(fname)
            ver = lab.group(1) if lab else (f"{int(f.group(1))}.{f.group(2)}" if f else None)
            if ver:
                drivers.append({
                    "version": ver, "date": "-".join(f.group(3, 4, 5)) if f else row_date,
                    "channel": "STABLE", "title": f"Driver Bundle v{ver}", "url": base + "/",
                    "download": dl, "sha": sha, "source": "resources",
                })
        prev_end = m.end()
    bios.sort(key=_release_key, reverse=True)
    drivers.sort(key=_release_key, reverse=True)
    return {"bios": bios, "driver": drivers[0] if drivers else None}


def fetch_resources_page(cfg: dict) -> dict | None:
    """Read and parse this model's Resources page (cached for two minutes so the
    BIOS and driver checks share one request). None if it can't be used."""
    url = ((cfg.get("sources") or {}).get("resources_url") or "").strip()
    if not url:
        return None
    now = time.monotonic()
    if _res_cache["url"] == url and now - _res_cache["at"] < 120:
        return _res_cache["data"]
    try:
        html = _get_text(url)
    except Exception as e:
        log.warning("Could not read Framework Resources page: %s", e)
        return None
    data = parse_resources_html(html, url)
    if not data["bios"] and not data["driver"]:
        log.warning("Resources page had no recognisable downloads; its layout may have changed.")
        data = None
    _res_cache.update(url=url, at=now, data=data)
    return data


# --- Framework community forum (betas, and backup for the Resources page) --

# Matches "BIOS 3.06 Release STABLE", "BIOS 4.01 Release BETA", etc.
_TITLE_RE = re.compile(r"BIOS\s+(\d+\.\d+)\s+Release\s+(STABLE|BETA)", re.IGNORECASE)
# Matches "Driver Bundle v2.00 2026_06_04 Release STABLE" (date optional).
_DRIVER_RE = re.compile(
    r"Driver\s+Bundle\s+v?(\d+\.\d+)(?:\s+(\d{4}_\d{2}_\d{2}))?.*?Release\s+(STABLE|BETA)",
    re.IGNORECASE,
)


def _parse_bios_title(title: str) -> dict | None:
    m = _TITLE_RE.search(title)
    return {"version": m.group(1), "channel": m.group(2).upper()} if m else None


def _parse_driver_title(title: str) -> dict | None:
    m = _DRIVER_RE.search(title)
    if not m:
        return None
    return {"version": m.group(1), "date": (m.group(2) or "").replace("_", "-"),
            "channel": m.group(3).upper()}


def _forum_release_post(thread_url: str, cfg: dict):
    """Read a release thread's first post. Returns (download_url, sha256) -- either
    may be None -- if it was posted by Framework's own forum group, or None if it
    wasn't (anyone can post a look-alike thread title). Raises if unreadable."""
    group = (cfg.get("sources") or {}).get("trusted_forum_group") or "Framework"
    data = _get_json(thread_url.rstrip("/") + ".json")
    posts = (data.get("post_stream") or {}).get("posts") or []
    post = posts[0] if posts else {}
    if (post.get("primary_group_name") or "") != group:
        log.warning("Ignoring forum thread not posted by the %s team: %s (by %s)",
                    group, thread_url, post.get("username"))
        return None
    html = post.get("cooked", "") or ""
    m = _DL_FRAMEWORK_RE.search(html)
    if not m:
        return None, None
    # Take the SHA256 from this file's own row: after the link, before the next one.
    nxt = _DL_FRAMEWORK_RE.search(html, m.end())
    s = _SHA256_RE.search(html, m.end(), nxt.start() if nxt else len(html))
    return m.group(0), (s.group(0) if s else None)


def _forum_latest(cfg: dict, search_url: str, parse, kind: str) -> dict | None:
    """Newest Framework-posted release thread for this model, honoring
    include_beta, with its download link and SHA256 filled in."""
    include_beta = cfg.get("include_beta", False)
    sources = cfg.get("sources") or {}
    base = (sources.get("community_base") or "https://community.frame.work").rstrip("/")
    try:
        topics = _get_json(search_url).get("topics") or []
    except Exception as e:
        log.warning("Could not search the forum for %s releases: %s", kind, e)
        return None
    candidates = []
    for topic in topics:
        title = topic.get("title", "") or ""
        if not _matches_model(title, cfg) or _WITHDRAWN_RE.search(title):
            continue  # another machine, or a held/pulled release
        rel = parse(title)
        if not rel or (rel["channel"] == "BETA" and not include_beta):
            continue
        slug, tid = topic.get("slug"), topic.get("id")
        if not (slug and tid):
            continue
        rel.update(title=title, url=f"{base}/t/{slug}/{tid}", source="forum")
        candidates.append(rel)
    candidates.sort(key=_release_key, reverse=True)
    for rel in candidates[:5]:
        try:
            post = _forum_release_post(rel["url"], cfg)
        except Exception as e:
            log.warning("Could not read forum thread %s: %s", rel["url"], e)
            return None  # don't silently fall back to an older release
        if post is None:
            continue  # not posted by Framework -- skip it
        rel["download"], rel["sha"] = post
        return rel
    return None


# --- latest BIOS / driver bundle ------------------------------------------

def fetch_latest_bios(cfg: dict) -> dict | None:
    """Newest BIOS for this model as {'version','channel','title','url',
    'download','sha','source'}, or None if no source could be read.

    Stable releases come from Framework's Resources page. Framework-posted forum
    threads add betas (when include_beta is on) and cover for the Resources page
    if it can't be read or hasn't caught up yet."""
    include_beta = cfg.get("include_beta", False)
    official = None
    for rel in (fetch_resources_page(cfg) or {}).get("bios", []):
        if rel["channel"] == "BETA" and not include_beta:
            continue
        official = rel
        break
    forum = None
    url = (cfg.get("sources") or {}).get("community_search_url")
    if url:
        forum = _forum_latest(cfg, url, _parse_bios_title, "BIOS")
    best = _pick_newer(official, forum)
    if best:
        log.info("Latest BIOS: %s (%s, from %s)", best["version"], best["channel"], best["source"])
    else:
        log.warning("Couldn't determine the latest BIOS from any source.")
    return best


def fetch_latest_driver_bundle(cfg: dict) -> dict | None:
    """Newest Windows driver bundle as {'version','date','channel','title','url',
    'download','sha','source'}, or None. Same sources as the BIOS check.

    Note: there's no reliable way to read the *installed* bundle version on
    Windows, so this is used for 'a new bundle was published' notifications, not
    installed-vs-latest comparison.
    """
    official = (fetch_resources_page(cfg) or {}).get("driver")
    forum = None
    url = (cfg.get("sources") or {}).get("driver_search_url")
    if url:
        forum = _forum_latest(cfg, url, _parse_driver_title, "driver bundle")
    best = _pick_newer(official, forum)
    if best:
        log.info("Latest driver bundle: %s %s (from %s)", best["version"],
                 best.get("date", ""), best["source"])
    return best


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


# --- app self-update (this program's own GitHub releases) ----------------

def fetch_latest_app_release(repo: str):
    """Latest release of THIS app from its GitHub repo ('owner/repo').
    Returns {'version','url','download'} (download = the setup .exe asset URL),
    or None. Never raises."""
    repo = (repo or "").strip().strip("/")
    if not repo or "/" not in repo:
        return None
    api = "https://api.github.com/repos/{}/releases/latest".format(repo)
    try:
        data = _get_json(api, accept="application/vnd.github+json")
    except Exception as e:
        log.info("App update check failed (%s): %s", repo, e)
        return None
    if not isinstance(data, dict):
        return None
    tag = data.get("tag_name") or data.get("name")
    if not tag:
        return None
    # Prefer a "setup" .exe asset; fall back to any .exe.
    dl = None
    for a in data.get("assets") or []:
        n = (a.get("name") or "").lower()
        if n.endswith(".exe"):
            url = a.get("browser_download_url")
            if "setup" in n:
                dl = url
                break
            dl = dl or url
    return {"version": tag, "url": data.get("html_url"), "download": dl}
