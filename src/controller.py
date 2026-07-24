"""wire keywatch -> capture -> overlay, plus control hotkeys

the tk root and overlay live on the main thread. keywatch (Tab) and the
RegisterHotKey listener run on their own threads and never touch a widget,
they marshal onto the tk thread via root.after. OCR runs off the tk thread so
a read never freezes the overlay. one read at a time (a busy read is skipped).
"""

import argparse
import ctypes
import signal
import sys
import threading
import tkinter as tk
from ctypes import wintypes

from src import capture, config_io, keywatch
from src.overlay import DebugOverlay, OverlayWindow, frame_count
from src.paths import data_dir, ensure_user_dirs, maps_present
from src.version import __version__

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012


class HotkeyListener(threading.Thread):
    """RegisterHotKey + message pump, fine for our non-game control keys"""

    def __init__(self, bindings):
        super().__init__(daemon=True)
        self.bindings = bindings  # {id: (vk, callback)}
        self._tid = None
        self._ready = threading.Event()

    def run(self):
        self._tid = _kernel32.GetCurrentThreadId()
        for hid, (vk, _cb, label) in self.bindings.items():
            if not _user32.RegisterHotKey(None, hid, 0, vk):
                print(
                    f"hotkey {label} failed to register, another app owns it "
                    f"(rebind it in config)"
                )
        self._ready.set()
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_HOTKEY:
                b = self.bindings.get(msg.wParam)
                if b:
                    b[1]()
        for hid in self.bindings:
            _user32.UnregisterHotKey(None, hid)

    def stop(self):
        self._ready.wait(timeout=2)
        if self._tid:
            _user32.PostThreadMessageW(self._tid, _WM_QUIT, 0, 0)


def _creators(entry):
    """distinct creators for a map in first-seen order"""
    seen = []
    for o in entry["overlays"]:
        if o["creator"] not in seen:
            seen.append(o["creator"])
    return seen


def _variations(entry, creator):
    return [o for o in entry["overlays"] if o["creator"] == creator]


class Controller:
    def __init__(self, cfg, debug=False):
        self.cfg = cfg
        self.debug = debug
        o = cfg.get("overlay", {})
        self.monitor = o.get("monitor", 0)
        # auto mode watches the HUD key and OCRs the map, manual mode just shows one chosen map
        self.auto_mode = o.get("auto_mode", True)
        self.manual_map = o.get("map", "")
        self.index = capture.load_index()
        self.matcher = capture.build_matcher(self.index)
        self.entry = None
        self.creator_i = 0
        self.views = []  # flattened (overlay record, frame index) for the creator
        self.view_i = 0
        self._read_lock = threading.Lock()

        self.root = tk.Tk()
        self.root.withdraw()  # only the overlay Toplevel is ever shown
        bounds = capture.monitor_bounds(self.monitor)
        self.overlay = OverlayWindow(self.root, cfg, bounds, on_move=self._save_position)
        self.debug_overlay = self._build_debug_overlay(bounds) if debug else None

        self.keywatch = keywatch.KeyWatcher(
            cfg, on_read=self._do_read,
            on_skip=self._log_skip,
            on_state=self._on_scan_state,
            on_no_match=self._on_no_match
        )
        self.hotkeys = self._build_hotkeys()

    def _build_debug_overlay(self, bounds):
        # rectangles where anchor gate + map-name ocr look on the target monitor
        regions = [
            ("anchor", capture.anchor_region(bounds, self.cfg), "#00ffff"),
            ("map", capture.map_region(bounds, self.cfg), "#00ff00"),
        ]
        return DebugOverlay(self.root, regions)

    def _log_skip(self, reason):
        if self.debug:
            print(f"skip: {reason}")

    def _on_scan_state(self, scanning):
        # debug bars mark where capture looks, only worth showing mid-read
        if self.debug:
            print("scan: looking..." if scanning else "scan: done")
        if self.debug_overlay:
            self.root.after(0, lambda: self.debug_overlay.set_visible(scanning))

    def _build_hotkeys(self):
        hk = self.cfg.get("hotkeys", {})
        # map each configured action to an id, vk, and a tk-thread-marshaled call
        actions = [
            ("toggle_overlay", lambda: self.overlay.toggle()),
            ("cycle_variation", self._cycle_variation),
            ("cycle_creator", self._cycle_creator),
            ("force_read", self._force_read),
            ("move_overlay", lambda: self.overlay.toggle_drag()),
            ("quit", self._quit),
        ]
        bindings = {}
        for i, (name, fn) in enumerate(actions, start=1):
            key = hk.get(name)
            if not key:
                continue
            try:
                vk = keywatch.resolve_vk(key)
            except ValueError as e:
                print(e)
                continue
            bindings[i] = (vk, self._on_tk(fn), f"{name} ({key})")
        return HotkeyListener(bindings)

    def _on_tk(self, fn):
        """run fn on the tk thread, hotkey/key threads must not touch widgets"""
        return lambda: self.root.after(0, fn)

    # reads run off the tk thread, only the overlay update hops back on
    def _do_read(self):
        """one ocr attempt, returns True when a map matched (drives the scan loop)"""
        if not self._read_lock.acquire(blocking=False):
            return False
        try:
            entry = capture.capture_and_match(
                self.matcher, self.cfg, self.monitor,
                on_log=print, debug=self.debug
            )
        finally:
            self._read_lock.release()
        if entry:
            self.root.after(0, lambda: self._on_match(entry))
            return True
        return False

    def _force_read(self):
        if not self.auto_mode:
            return  # manual mode has no ocr to force
        threading.Thread(target=self._do_read, daemon=True).start()

    def _on_no_match(self):
        # session gave up, drop the stale callout instead of leaving it up
        self.root.after(0, self._clear)

    def _clear(self):
        self.entry = None
        self.views = []
        self.overlay.set_visible(False)

    def _on_match(self, entry):
        # a new map resets creator/variation to the configured preference
        self.entry = entry
        self.creator_i = self._preferred_creator_i(entry)
        self._build_views()
        self.view_i = self._preferred_view_i()
        self._render()

    def _entry_by_name(self, name):
        return next((e for e in self.index["maps"] if e["name"] == name), None)

    def _load_manual_map(self):
        # manual mode shows one chosen map, rendered up front then hidden until the toggle key reveals it
        entry = self._entry_by_name(self.manual_map) if self.manual_map else None
        if entry is None:
            maps = self.index["maps"]
            entry = maps[0] if maps else None
        if entry:
            self._on_match(entry)
            self.overlay.set_visible(False)

    def _preferred_creator_i(self, entry):
        want = self.cfg.get("overlay", {}).get("creator", "")
        creators = _creators(entry)
        return creators.index(want) if want in creators else 0

    def _build_views(self):
        # each record expands into one view per frame, so a multi-floor map
        # cycles floor-by-floor before moving to the next variation
        creator = _creators(self.entry)[self.creator_i]
        views = []
        for rec in _variations(self.entry, creator):
            path = data_dir() / rec["file"]
            n = frame_count(path) if path.exists() else 1
            views.extend((rec, fi) for fi in range(n))
        self.views = views

    def _preferred_view_i(self):
        want = str(self.cfg.get("preferred_variation", ""))
        for i, (rec, frame) in enumerate(self.views):
            if rec["label"] == want and frame == 0:
                return i
        return 0

    def _render(self):
        if not self.entry or not self.views:
            return
        rec, frame = self.views[self.view_i]
        creator = _creators(self.entry)[self.creator_i]
        path = data_dir() / rec["file"]
        if not path.exists():
            print(f"missing overlay file {path}")
            return
        n = frame_count(path)
        floor = f" floor {frame + 1}/{n}" if n > 1 else ""
        print(f"showing {self.entry['name']} [{creator} {rec['label']}{floor}]")
        self.overlay.show_image(str(path), frame)

    def _cycle_creator(self):
        if not self.entry:
            return
        creators = _creators(self.entry)
        self.creator_i = (self.creator_i + 1) % len(creators)
        self._build_views()
        self.view_i = 0
        self.cfg.setdefault("overlay", {})["creator"] = creators[self.creator_i]
        config_io.save(self.cfg)
        self._render()

    def _cycle_variation(self):
        if not self.entry or not self.views:
            return
        self.view_i = (self.view_i + 1) % len(self.views)
        self.cfg["preferred_variation"] = self.views[self.view_i][0]["label"]
        config_io.save(self.cfg)
        self._render()

    def _save_position(self, x, y):
        o = self.cfg.setdefault("overlay", {})
        o["x"], o["y"] = x, y
        config_io.save(self.cfg)
        print(f"overlay position saved {x},{y}")

    def _quit(self):
        # runs on the tk thread, ends mainloop so run()'s finally cleans up
        print("quitting")
        self.root.quit()

    def _sigint(self, *_):
        # ctrl+c fires on the main thread, marshal onto tk to end cleanly
        self.root.after(0, self._quit)

    def _keep_signals_alive(self):
        # tk mainloop blocks in C and won't run python signal handlers unless
        # the interpreter wakes periodically, so tick every 200ms
        self.root.after(200, self._keep_signals_alive)

    def run(self):
        signal.signal(signal.SIGINT, self._sigint)
        if self.auto_mode:
            self.keywatch.start()
        else:
            self._load_manual_map()
        self.hotkeys.start()
        self._keep_signals_alive()
        hk = self.cfg.get("hotkeys", {})
        print(f"smart-dbd-map-overlay {__version__}")
        if self.auto_mode:
            print(
                "running. tap your HUD key (Tab) to open the scoreboard, it reads the "
                "map while the HUD is up. tap Tab again to stop looking."
            )
        else:
            print(
                f"manual mode, auto ocr off. showing {self.manual_map or 'the first map'}, "
                f"tap {hk.get('toggle_overlay')} to show or hide it."
            )
        print(
            f"  {hk.get('toggle_overlay')} toggle  {hk.get('cycle_creator')} creator  "
            f"{hk.get('cycle_variation')} variation  {hk.get('force_read')} force read  "
            f"{hk.get('move_overlay')} move  {hk.get('quit')} quit  (or Ctrl+C)"
        )
        if self.debug:
            print("  debug on: while reading, cyan = anchor gate box, green = map-name box")
        try:
            self.root.mainloop()
        finally:
            if self.auto_mode:
                self.keywatch.stop()
            self.hotkeys.stop()


def _ensure_maps():
    # the exe ships without callouts, fetch them once
    if maps_present():
        return True
    print("map callouts are not downloaded yet.")
    print("they come from hens333.com and allmyperks.com, about 25 mb.")
    # a gui launch has no console to prompt on, so proceed there and only ask when run in a terminal
    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    if interactive:
        if input("download them now? [y/N] ").strip().lower() not in ("y", "yes"):
            print("exiting, nothing to show without the maps. run again to download")
            return False
    else:
        print("no console attached, downloading the callouts now...")
    from src import scraper
    scraper.main([])
    return maps_present()


def main():
    ap = argparse.ArgumentParser(prog="smart-dbd-map-overlay")
    ap.add_argument(
        "--debug", action="store_true",
        help="draw the OCR region rectangles and log every read attempt"
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()
    ensure_user_dirs()
    if not _ensure_maps():
        return
    cfg = config_io.load()
    Controller(cfg, debug=args.debug).run()


if __name__ == "__main__":
    main()
