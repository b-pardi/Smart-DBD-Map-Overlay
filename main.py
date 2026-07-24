"""dev + frozen entry point

fixes the two things that must happen before any real import:
give a windowed build a valid stdout (runw.exe hands it None),
and go per-monitor DPI aware so mss capture coords and tk/win32 placement agree on physical pixels.
"""

import os
import sys


def _fix_streams():
    # windowed pyinstaller build hands None for stdout/stderr, writes to None would crash. bind to the real
    # fd first so a redirected launch (the gui tees us to a log) is honored, only then fall back to null
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
    from src.controller import main as run
    run()


if __name__ == "__main__":
    main()
