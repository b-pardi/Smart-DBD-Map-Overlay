"""transparent click-through always-on-top callout window (tkinter + win32)

a borderless Toplevel using a magenta colorkey for transparency,
layered + transparent + noactivate ex-styles so clicks pass through to the game and it never steals focus,
and a 1s topmost re-assert to fight the game reclaiming z-order.
drag mode drops click-through so the user can reposition it.
requires borderless windowed DBD, exclusive fullscreen eats overlays.
"""

import ctypes
import tkinter as tk

from PIL import Image, ImageTk

COLORKEY = "#ff00ff"  # magenta, transparent areas key out to this, rare in art
_COLORKEY_RGB = (255, 0, 255)

_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080  # keep it off the taskbar and alt-tab

_HWND_TOPMOST = -1
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_FRAMECHANGED = 0x0020
_SWP_NOACTIVATE = 0x0010

_GA_ROOT = 2  # walk up to the real top-level window

_user32 = ctypes.windll.user32
_user32.GetWindowLongPtrW.restype = ctypes.c_longlong
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_longlong
_user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
_user32.GetAncestor.restype = ctypes.c_void_p
_user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]


def _set_clickthrough(hwnd, on, layered=True):
    """noactivate + toolwindow, transparent toggles hit-testing

    layered=False for solid opaque windows,
    a layered window whose colorkey drops on a frame-change paints black,
    ruinous on a full-screen surface
    """
    ex = _user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
    ex |= _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW
    if layered:
        ex |= _WS_EX_LAYERED
    if on:
        ex |= _WS_EX_TRANSPARENT
    else:
        ex &= ~_WS_EX_TRANSPARENT
    _user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, ex)
    # frame-change so the new ex-style is committed to hit-testing now
    _user32.SetWindowPos(
        hwnd, 0, 0, 0, 0, 0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER
        | _SWP_NOACTIVATE | _SWP_FRAMECHANGED
    )
    return _user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)


def _set_topmost(hwnd):
    _user32.SetWindowPos(
        hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
    )


def frame_count(image_path):
    """number of frames in a callout, >1 means a multi-floor map"""
    try:
        with Image.open(image_path) as im:
            return getattr(im, "n_frames", 1)
    except OSError:
        return 1


class OverlayWindow:
    def __init__(self, root, cfg, bounds, on_move=None):
        self.cfg = cfg
        self.bounds = bounds
        self.on_move = on_move or (lambda x, y: None)
        o = cfg.get("overlay", {})
        self.size = int(o.get("size", 250))
        # default to a corner of the target monitor until the user drags it
        self.x = o["x"] if o.get("x") is not None else bounds["left"] + 40
        self.y = o["y"] if o.get("y") is not None else bounds["top"] + 40
        self._photo = None
        self._visible = False
        self._drag = False
        self._alive = True

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=COLORKEY)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", COLORKEY)
        self.win.attributes("-alpha", float(o.get("opacity", 0.5)))
        self.label = tk.Label(self.win, bg=COLORKEY, bd=0, highlightthickness=0)
        self.label.pack()
        self.win.geometry(f"+{self.x}+{self.y}")
        self.win.withdraw()  # nothing to show until the first match
        self._hwnd = None
        self._styled = False

    def _root_hwnd(self):
        # tk wraps a toplevel, the wrapper is what hit-tests and activates
        hwnd = self.win.winfo_id()
        return _user32.GetAncestor(hwnd, _GA_ROOT) or hwnd

    def _ensure_styled(self):
        # reapply on every show, re-asserting overrideredirect can recreate the
        # hwnd and drop the ex-styles
        self.win.update_idletasks()
        self._hwnd = self._root_hwnd()
        self._set_clickthrough(True)
        if not self._styled:
            self._styled = True
            self._reassert_topmost()

    # win32 ex-style plumbing
    def _set_clickthrough(self, on):
        return _set_clickthrough(self._hwnd, on)

    def exstyle_diag(self):
        """readback of the applied ex-style flags, for the live probe"""
        ex = _user32.GetWindowLongPtrW(self._hwnd, _GWL_EXSTYLE)
        return {
            "hwnd": self._hwnd,
            "parent": _user32.GetParent(self._hwnd),
            "layered": bool(ex & _WS_EX_LAYERED),
            "transparent": bool(ex & _WS_EX_TRANSPARENT),
            "noactivate": bool(ex & _WS_EX_NOACTIVATE),
            "toolwindow": bool(ex & _WS_EX_TOOLWINDOW),
        }

    def _reassert_topmost(self):
        if not self._alive:
            return
        _set_topmost(self._hwnd)
        self.win.after(1000, self._reassert_topmost)

    def show_image(self, image_path, frame=0):
        """render a callout, transparent pixels flattened onto the colorkey

        multi-frame webp (midwich floors) is one file, seek picks the floor
        """
        im = Image.open(image_path)
        try:
            im.seek(frame)
        except (EOFError, ValueError):
            pass  # single frame or out of range, fall back to what is open
        im = im.convert("RGBA")
        im.thumbnail((self.size, self.size), Image.LANCZOS)
        bg = Image.new("RGBA", im.size, _COLORKEY_RGB + (255,))
        bg.alpha_composite(im)
        self._photo = ImageTk.PhotoImage(bg.convert("RGB"))
        self.label.configure(image=self._photo)
        self.win.geometry(f"{im.width}x{im.height}+{self.x}+{self.y}")
        self.set_visible(True)

    def set_visible(self, on):
        self._visible = on
        if on:
            self.win.deiconify()
            self.win.overrideredirect(True)  # re-assert, tk can drop it on map
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._ensure_styled()
        else:
            self.win.withdraw()

    def toggle(self):
        self.set_visible(not self._visible)

    def set_opacity(self, opacity):
        self.win.attributes("-alpha", float(opacity))

    # drag placement: drop click-through, move on drag, persist on exit
    def toggle_drag(self):
        if not self._visible:
            self.set_visible(True)  # also styles the window on first show
        self._ensure_styled()
        self._drag = not self._drag
        self._set_clickthrough(not self._drag)
        if self._drag:
            self.win.attributes("-alpha", 1.0)
            self.label.configure(cursor="fleur")
            self.win.bind("<ButtonPress-1>", self._drag_start)
            self.win.bind("<B1-Motion>", self._drag_move)
        else:
            self.win.unbind("<ButtonPress-1>")
            self.win.unbind("<B1-Motion>")
            self.label.configure(cursor="")
            self.set_opacity(self.cfg.get("overlay", {}).get("opacity", 0.5))
            self.on_move(self.x, self.y)

    def _drag_start(self, e):
        self._grab = (e.x, e.y)

    def _drag_move(self, e):
        self.x = self.win.winfo_pointerx() - self._grab[0]
        self.y = self.win.winfo_pointery() - self._grab[1]
        self.win.geometry(f"+{self.x}+{self.y}")

    def destroy(self):
        self._alive = False
        self.win.destroy()


class DebugOverlay:
    """thin solid outlines of the OCR regions, shown only while a read runs under --debug

    each region is framed by four opaque bars rather than one full-screen layered window,
    so there is no colorkey to drop and nothing big to black out the screen.
    bars are click-through and topmost like the callout.
    """

    _THICK = 3

    def __init__(self, root, regions):
        self.root = root
        self._alive = True
        self._visible = False
        self._wins = []
        for _name, region, color in regions:
            self._frame(region, color)
        self.set_visible(False)  # only appear while capturing
        self._reassert_topmost()

    def _frame(self, region, color):
        # top, bottom, left, right bars at virtual-screen coords
        x, y, w, h = region["left"], region["top"], region["width"], region["height"]
        t = self._THICK
        for rx, ry, rw, rh in ((x, y, w, t), (x, y + h - t, w, t),
                               (x, y, t, h), (x + w - t, y, t, h)):
            self._bar(rx, ry, rw, rh, color)

    def _bar(self, x, y, w, h, color):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=color)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.update_idletasks()
        _set_clickthrough(win.winfo_id(), True, layered=False)
        self._wins.append(win)

    def set_visible(self, on):
        self._visible = on
        for win in self._wins:
            if on:
                win.deiconify()
                win.overrideredirect(True)  # tk can drop it on map
                win.attributes("-topmost", True)
            else:
                win.withdraw()

    def _reassert_topmost(self):
        if not self._alive:
            return
        if self._visible:
            for win in self._wins:
                _set_topmost(win.winfo_id())
        self.root.after(1000, self._reassert_topmost)

    def destroy(self):
        self._alive = False
        for win in self._wins:
            win.destroy()
        self._wins = []
