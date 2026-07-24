"""update check against the github releases api, no self-install.

we ship onefile so there is nothing to swap in place, the manual button just reports status and, when
a newer release exists, opens the releases page. split so the ui stays thin: check hits the api and
decides newer purely on a worker thread and never touches tk, check_async runs it off-thread and
marshals the result back through app.after.
"""

import re
import threading
import tkinter.messagebox as messagebox
import webbrowser

from src.version import __version__, GITHUB_REPO

# requests pulls in a few hundred ms and is only needed when the user actually checks, so it is
# imported inside the worker functions, never at ui startup

_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"


def current_version():
    return __version__


def _parse(tag):
    """"v0.1.0-alpha" -> ((0,1,0), 1|0 release-flag, "alpha"), None if it isn't an X.Y.Z tag.

    the release-flag sorts a plain X.Y.Z above any X.Y.Z-prerelease, and prerelease strings sort
    against each other lexically, good enough for alpha/beta/rc.
    """
    m = re.match(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(.*))?$", tag.strip().lstrip("vV"))
    if not m:
        return None
    nums = tuple(int(x) for x in m.group(1, 2, 3))
    pre = (m.group(4) or "").strip()
    return (nums, 0 if pre else 1, pre)


def is_newer(latest_tag, current=None):
    """is latest_tag a newer version than the running one.

    falls back to a plain inequality if either tag doesn't parse, so a weird tag still surfaces as
    something changed rather than silently never updating.
    """
    cur = current or current_version()
    lp, cp = _parse(latest_tag), _parse(cur)
    if lp is None or cp is None:
        return latest_tag.lstrip("vV") != cur.lstrip("vV")
    return lp > cp


def check(timeout=8):
    """query the releases list (prereleases included) and return the highest-version non-draft.

    returns a dict {tag, name, body, page, newer} or None when the repo has no usable release. raises
    on network/http errors so the caller can decide whether to surface them.
    """
    import requests

    r = requests.get(_API, headers={"Accept": "application/vnd.github+json"}, timeout=timeout)
    r.raise_for_status()

    # the api orders by creation date not version, so a hotfix on an old line can land first, pick
    # the max by version instead of trusting the first result
    best = None
    for rel in r.json():
        if rel.get("draft"):
            continue
        tag = rel.get("tag_name") or ""
        if best is None or is_newer(tag, best.get("tag_name") or ""):
            best = rel
    if best is None:
        return None

    tag = best.get("tag_name") or ""
    return {
        "tag": tag,
        "name": best.get("name") or tag,
        "body": best.get("body") or "",
        "page": best.get("html_url"),
        "newer": is_newer(tag),
    }


def check_async(app, on_result, timeout=8):
    """run check() on a worker thread and deliver (info_or_None, err_or_None) to on_result.

    tk isn't thread-safe, so the worker only ever hands the result back through app.after.
    """

    def worker():
        try:
            info = check(timeout=timeout)
            app.after(0, lambda: on_result(info, None))
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            app.after(0, lambda: on_result(None, msg))

    threading.Thread(target=worker, daemon=True).start()


def run_check(app, button, done_text="Check for updates"):
    """the shared manual update check: disable button, check off-thread, then report the outcome.

    the nav-rail button and the About button both call this so a check behaves the same everywhere,
    newer offers the releases page, current says so, an error shows itself. app is the tk root so the
    worker can marshal back through app.after.
    """
    button.configure(state="disabled", text="Checking...")

    def on_result(info, err):
        button.configure(state="normal", text=done_text)
        if err:
            messagebox.showerror("update check failed", err)
            return
        if not info or not info.get("newer"):
            messagebox.showinfo("up to date", f"You're on the latest version ({current_version()}).")
            return
        if info.get("page") and messagebox.askyesno(
            "update available",
            f"A new version ({info['tag']}) is available (you have {current_version()}).\n\n"
            "Open the download page?",
        ):
            webbrowser.open(info["page"])

    check_async(app, on_result, timeout=timeout)
