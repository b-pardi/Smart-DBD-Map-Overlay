"""dev + frozen entry point

fixes the two things that must happen before any real import:
give a windowed build a valid stdout (runw.exe hands it None),
and go per-monitor DPI aware so mss capture coords and tk/win32 placement agree on physical pixels.
"""

import os
import sys


def _fix_streams():
    # windowed pyinstaller build has no console, writes to None would crash
    if sys.stdout is None or sys.stderr is None:
        null = open(os.devnull, "w")
        sys.stdout = sys.stdout or null
        sys.stderr = sys.stderr or null


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
