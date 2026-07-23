"""daemon thread watching the HUD key via GetAsyncKeyState polling

a bare HUD-key press (default Tab) opens a scan session:
it retries the OCR read every retry_interval up to max_retries then gives up,
so it rides out the HUD fade-in instead of firing one blind read.
a session that gives up with no match clears any stale callout.
a second press (after release) closes an open session.
passive: never RegisterHotKey on Tab, that steals it from the game.
modifier-gated, bare key only.
"""

import ctypes
import threading
import time

_user32 = ctypes.windll.user32
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

_DOWN = 0x8000

# named keys the config might use, letters/digits resolve by ord below
_VK_NAMES = {
    "tab": 0x09, "space": 0x20, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

# shift, ctrl, alt, lwin, rwin, any held one means it isn't a bare press
_MODIFIER_VKS = (0x10, 0x11, 0x12, 0x5B, 0x5C)

_POLL_S = 0.01  # ~100Hz


def resolve_vk(key):
    """virtual-key code from a config key name like 'tab' or 'f'"""
    k = str(key).strip().lower()
    if k in _VK_NAMES:
        return _VK_NAMES[k]
    if len(k) == 1 and (k.isalpha() or k.isdigit()):
        return ord(k.upper())
    raise ValueError(f"unknown hud_key {key!r}")


def _down(vk):
    return bool(_user32.GetAsyncKeyState(vk) & _DOWN)


def _modifier_held():
    return any(_down(vk) for vk in _MODIFIER_VKS)


class KeyWatcher(threading.Thread):
    """polls the HUD key, runs a retrying scan session per bare press

    on_read() does one OCR attempt and returns True when a map matched.
    on_state(bool) fires when a session opens or closes, for debug/status.
    on_no_match() fires when a session gives up with nothing matched.
    """

    def __init__(self, cfg, on_read, on_skip=None, on_state=None, on_no_match=None):
        super().__init__(daemon=True)
        self.vk = resolve_vk(cfg.get("hud_key", "tab"))
        self.on_read = on_read
        self.on_skip = on_skip or (lambda reason: None)
        self.on_state = on_state or (lambda scanning: None)
        self.on_no_match = on_no_match or (lambda: None)
        s = cfg.get("scan", {})
        self.post_press_delay_s = float(s.get("post_press_delay_s", 0.05))
        self.retry_interval_s = float(s.get("retry_interval_s", 0.15))
        self.max_retries = int(s.get("max_retries", 3))
        self.rescan_cooldown_s = float(s.get("rescan_cooldown_s", 1.0))
        self._scanning = False  # menu open, toggled by the hud key
        self._looking = False  # read loop active, off once matched but menu stays open
        self._last_scan_end = 0.0
        self._lock = threading.Lock()
        self._wake = threading.Event()  # start-of-session signal to the worker
        self._stop = threading.Event()
        # one long-lived worker so its mss handle is created once, not per session
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)

    def stop(self):
        self._stop.set()
        self._scanning = False
        self._looking = False
        self._wake.set()

    def run(self):
        self._worker.start()
        was_down = _down(self.vk)  # avoid firing if key already held at start
        while not self._stop.is_set():
            now_down = _down(self.vk)
            if now_down and not was_down:
                self._on_press_edge()
            was_down = now_down
            time.sleep(_POLL_S)

    def _on_press_edge(self):
        # bare key only, a modifier means shift+tab etc, swallow it
        if _modifier_held():
            self.on_skip("modifier held")
            return
        if self._scanning:
            self._end_scan()  # menu closed, do not re-read
            return
        if time.monotonic() - self._last_scan_end < self.rescan_cooldown_s:
            self.on_skip("cooldown")
            return
        self._start_scan()

    def _start_scan(self):
        with self._lock:
            if self._scanning:
                return
            self._scanning = True
            self._looking = True
        self.on_state(True)
        self._wake.set()

    def _stop_looking(self, reason=None):
        # end the read loop but keep the session open for the closing key press
        with self._lock:
            fire = self._looking
            self._looking = False
        if fire:
            self.on_state(False)
        if reason:
            self.on_skip(reason)

    def _end_scan(self, reason=None):
        with self._lock:
            if not self._scanning:
                return
            self._scanning = False
            fire = self._looking
            self._looking = False
            self._last_scan_end = time.monotonic()
        if fire:
            self.on_state(False)
        if reason:
            self.on_skip(reason)

    def _worker_loop(self):
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            if self._stop.is_set():
                return
            if self._scanning:
                self._run_session()

    def _run_session(self):
        # retry a few times while the HUD may still be fading, then give up
        time.sleep(self.post_press_delay_s)
        attempts = 0
        while self._looking and self._scanning and not self._stop.is_set():
            if self.on_read():
                self._stop_looking()  # matched, keep the menu session open
                return
            attempts += 1
            if attempts >= self.max_retries:
                self._stop_looking(f"no map after {self.max_retries} reads")
                self.on_no_match()
                return
            time.sleep(self.retry_interval_s)
