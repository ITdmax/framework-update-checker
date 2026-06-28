"""Windows toast notifications.

Uses winotify (works on Win10/11, supports a clickable action button that can
open the release notes). Falls back to logging if winotify isn't available so
the rest of the app still works.
"""
import logging

log = logging.getLogger("fuc.notify")

APP_ID = "Framework Update Checker"

try:
    from winotify import Notification, audio
    _HAVE = True
except Exception:  # not installed, or non-Windows during development
    _HAVE = False


def notify(title: str, message: str, url: str | None = None,
           button_label: str = "Open release notes") -> None:
    if not _HAVE:
        log.info("NOTIFY | %s | %s | %s", title, message, url or "")
        return
    try:
        toast = Notification(app_id=APP_ID, title=title, msg=message, duration="short")
        try:
            toast.set_audio(audio.Default, loop=False)
        except Exception:
            pass
        if url:
            toast.add_actions(label=button_label, launch=url)
        toast.show()
    except Exception as e:
        log.warning("Toast failed (%s); message was: %s - %s", e, title, message)
