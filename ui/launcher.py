"""spawn the overlay, the scraper, and the self-test as separate processes.

the gui never runs ocr or the scraper itself, it shells out so their stdout logs, progress bars, and the
first-run download prompt get a real console. frozen we re-invoke our own exe with a hidden flag, from
source we run the module. the overlay is the one long-lived child we track so the Launch button can
reflect it running.
"""

import os
import subprocess
import sys
import threading

from src import paths

# no console for a child whose output we capture, so a windowed launch never flashes one
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# the overlay child we own, guarding a double-launch, cleared once it exits
_proc = None


def _self_args(flag, module):
    """argv to re-enter our own code: the frozen exe re-runs itself with flag, from source run module"""
    if paths.is_frozen():
        return [sys.executable, flag]
    return [sys.executable, "-m", module]


def is_running():
    """true while our launched overlay child is still alive"""
    return _proc is not None and _proc.poll() is None


def launch_overlay():
    """start the overlay with its output teed to the log, returning the child or the live one.

    the overlay's stdout and stderr go to overlay_log_path so the Debug panel can tail them, and since the
    child holds its own handle to that file it keeps logging even after this gui closes. stdin is closed
    (no console), so the overlay's first-run download runs unprompted, see controller._ensure_maps.
    """
    global _proc
    if is_running():
        return _proc
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    log = open(paths.overlay_log_path(), "w", encoding="utf-8")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}  # flush per line so the tail stays live
    args = [sys.executable, "--run-overlay"] if paths.is_frozen() else [sys.executable, "-u", "main.py"]
    try:
        _proc = subprocess.Popen(
            args,
            cwd=str(paths.resource_path()),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=_NO_WINDOW,
        )
    finally:
        log.close()  # the child kept its own dup, so writing outlives this handle
    return _proc


def stop_overlay():
    """terminate the overlay child if we own a live one"""
    global _proc
    if is_running():
        _proc.terminate()
    _proc = None


def run_scraper():
    """refresh the callouts in a new console so the download progress and any prompts stay visible"""
    subprocess.Popen(
        _self_args("--run-scraper", "src.scraper"),
        cwd=str(paths.resource_path()),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def run_selftest(app, on_result, timeout=120):
    """run the headless self-test off-thread, deliver (output_text, ok_bool) back through app.after.

    output is captured rather than shown in a console so the gui can render it in-app, tk is only ever
    touched through app.after since the work runs on a worker thread.
    """

    def worker():
        try:
            proc = subprocess.run(
                _self_args("--run-selftest", "src.selftest"),
                cwd=str(paths.resource_path()),
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            app.after(0, lambda: on_result(out.strip(), proc.returncode == 0))
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            app.after(0, lambda: on_result(msg, False))

    threading.Thread(target=worker, daemon=True).start()
