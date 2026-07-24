"""main exe entry point, routes the gui vs the hidden overlay process.

fixes the two things that must happen before any real import, mirroring main.py: give a windowed
build a valid stdout (runw.exe hands it None), and go per-monitor DPI aware so mss capture coords and
tk/win32 placement agree on physical pixels. then route: the gui launch button relaunches this exe
with --run-overlay to spawn the headless overlay, everything else runs the settings gui. imports stay
lazy so overlay mode never pulls in customtkinter and gui mode never pulls in the ocr chain.
"""

import os
import sys


def _fix_streams():
    # windowed build hands None for stdout/stderr, writes to None would crash. bind to the real fd first
    # so the overlay's output reaches the log file the gui redirected it to, only then fall back to null
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name) is not None:
            continue
        try:
            stream = os.fdopen(fd, "w", buffering=1, encoding="utf-8", errors="replace")
        except OSError:
            stream = open(os.devnull, "w")
        setattr(sys, name, stream)


def _dpi_aware():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v1
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _fix_streams()
    _dpi_aware()
    # hidden flags let the frozen exe re-invoke its own bundled src for the gui's shell-outs
    if "--run-overlay" in sys.argv:
        # drop the flag so the overlay's argparse doesn't choke on it
        sys.argv = [a for a in sys.argv if a != "--run-overlay"]
        from src.controller import main as run_overlay
        run_overlay()
    elif "--run-scraper" in sys.argv:
        sys.argv = [a for a in sys.argv if a != "--run-scraper"]
        from src.scraper import main as run_scraper
        run_scraper([])
    elif "--run-selftest" in sys.argv:
        from src.selftest import main as run_selftest
        raise SystemExit(run_selftest())
    else:
        from ui.app import run
        run()


if __name__ == "__main__":
    main()
