"""Windows toast notifications.

Uses winotify (Win10/11). Supports a body-click target (so clicking the toast
does something instead of just dismissing) and one or more action buttons that
can launch a URL or a local installer via the file:/// protocol. Falls back to
logging if winotify isn't available so the rest of the app still works.
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
           button_label: str = "Open release notes",
           launch: str | None = None, actions=None) -> None:
    """Show a toast.

    launch:  URL/URI invoked when the toast body is clicked.
    actions: list of (label, link) tuples -> action buttons. 'link' may be an
             http(s) URL or a file:/// URI (to run a downloaded installer).
    url/button_label: legacy single-button convenience; appended as a button.
    """
    if not _HAVE:
        log.info("NOTIFY | %s | %s | %s", title, message, launch or url or "")
        return
    try:
        body = launch or url or ""
        toast = Notification(app_id=APP_ID, title=title, msg=message,
                             duration="short", launch=body)
        try:
            toast.set_audio(audio.Default, loop=False)
        except Exception:
            pass

        acts = list(actions or [])
        if url:
            acts.append((button_label, url))
        # Windows shows at most 5 action buttons; keep it sane.
        for label, link in acts[:5]:
            if label and link:
                try:
                    toast.add_actions(label, link)  # positional: works regardless
                except Exception as e:               # of the param name across versions
                    log.debug("add_actions(%s) failed: %s", label, e)

        toast.show()
    except Exception as e:
        log.warning("Toast failed (%s); message was: %s - %s", e, title, message)
