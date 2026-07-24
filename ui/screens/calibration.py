"""calibration screen: the visual OCR-region picker over a live screenshot of the target monitor.

grab the monitor the Overlay tab points at, scale it into a canvas, and draw three boxes: green for the
"REALM - MAP" name box at the bottom center, cyan for the top-left PLAYERS/QUESTS tabs the read gates on,
and amber for the callout overlay itself so its landing spot is placed here too. the forward math for the
two capture regions mirrors src.capture.map_region / anchor_region (not imported, so the gui stays clear
of the numpy/tesserocr chain), and Save applies the exact inverse so the round-trip is lossless. all
edits land on the shared config, the base Screen owns the header, dirty star, and save flow.
"""

import tkinter as tk
import tkinter.messagebox as messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from .. import config_bind, theme
from .base import Screen, SaveAbort

CANVAS_MAX_W, CANVAS_MAX_H = 900, 460  # bounds the screenshot is scaled to fit inside

GREEN = "#00ff00"  # the map-name box, over the bottom-center "REALM - MAP" text
CYAN = "#00ffff"   # the anchor box, over the top-left PLAYERS/QUESTS tabs
# the overlay proxy uses the theme accent (amber) so it reads apart from the two capture boxes


def _monitor_bounds(monitor, sct):
    """virtual-screen rect of the target monitor, mirroring src.capture.monitor_bounds.

    monitor 0 is the os primary at (0,0), monitor >= 1 forces that mss index for multi-display setups.
    kept in lockstep with capture so the picker frames the same pixels the live read will.
    """
    mons = sct.monitors
    if monitor and 0 < monitor < len(mons):
        m = mons[monitor]
    else:
        m = next((mm for mm in mons[1:] if mm["left"] == 0 and mm["top"] == 0), mons[1])
    return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}


class _DragBox:
    """a rectangle on the canvas, movable by its body and optionally resizable by a bottom-right grip.

    coords are held in canvas pixels and clamped to the canvas, the screen converts them to monitor px on
    save. a resizable box carries the grip raised above the body so a corner drag resizes rather than
    moves, a move-only box (the overlay proxy) has no grip and keeps a fixed size. an optional text tag
    names the box and shares the body drag so the label is never a dead spot. on_change fires after a user
    drag so the screen can flag the dirty star, set_coords stays silent for programmatic resyncs.
    """

    GRIP = 9
    MIN = 12

    def __init__(self, canvas, x0, y0, x1, y1, color, resizable=True, label=None, on_change=None):
        self.c = canvas
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self._on_change = on_change or (lambda: None)
        self._last = (0, 0)
        self.rect = canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
        canvas.tag_bind(self.rect, "<ButtonPress-1>", self._body_press)
        canvas.tag_bind(self.rect, "<B1-Motion>", self._body_drag)

        self.grip = None
        if resizable:
            self.grip = canvas.create_rectangle(0, 0, 0, 0, fill=color, outline=color)
            canvas.tag_bind(self.grip, "<ButtonPress-1>", self._grip_press)
            canvas.tag_bind(self.grip, "<B1-Motion>", self._grip_drag)

        self.text = None
        if label:
            self.text = canvas.create_text(
                x0 + 3, y0 + 2, text=label, fill=color, anchor="nw", font=("Segoe UI", 9, "bold"))
            canvas.tag_bind(self.text, "<ButtonPress-1>", self._body_press)
            canvas.tag_bind(self.text, "<B1-Motion>", self._body_drag)

        self._render()

    @property
    def _cw(self):
        return int(self.c.cget("width"))

    @property
    def _ch(self):
        return int(self.c.cget("height"))

    def _render(self):
        self.c.coords(self.rect, self.x0, self.y0, self.x1, self.y1)
        self.c.tag_raise(self.rect)
        if self.grip is not None:
            self.c.coords(self.grip, self.x1 - self.GRIP, self.y1 - self.GRIP, self.x1, self.y1)
            self.c.tag_raise(self.grip)
        if self.text is not None:
            self.c.coords(self.text, self.x0 + 3, self.y0 + 2)
            self.c.tag_raise(self.text)

    def _body_press(self, e):
        self._last = (e.x, e.y)

    def _body_drag(self, e):
        dx, dy = e.x - self._last[0], e.y - self._last[1]
        self._last = (e.x, e.y)
        w, h = self.x1 - self.x0, self.y1 - self.y0
        nx0 = min(max(0, self.x0 + dx), self._cw - w)
        ny0 = min(max(0, self.y0 + dy), self._ch - h)
        self.x0, self.y0, self.x1, self.y1 = nx0, ny0, nx0 + w, ny0 + h
        self._render()
        self._on_change()

    def _grip_press(self, e):
        self._last = (e.x, e.y)

    def _grip_drag(self, e):
        self.x1 = min(max(self.x0 + self.MIN, e.x), self._cw)
        self.y1 = min(max(self.y0 + self.MIN, e.y), self._ch)
        self._render()
        self._on_change()

    def coords(self):
        return (self.x0, self.y0, self.x1, self.y1)

    def set_coords(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self._render()


class CalibrationScreen(Screen):
    def __init__(self, master, app):
        super().__init__(master, app, "Calibration", "place the boxes on the screenshot, then save")
        self.canvas = None
        self.green = None
        self.cyan = None
        self.overlay_box = None
        self.bounds = None  # virtual-screen rect of the loaded monitor, stashed for the overlay math
        self._photo = None  # keep a ref so tk doesn't gc the screenshot
        self.k = 1.0        # canvas px per monitor px
        self.W = self.H = 0
        self._loaded_mon = None

        # header at row 0, help at row 1, canvas at row 2, save bar at row 3
        self.grid_rowconfigure(2, weight=1)

        help_frame = ctk.CTkFrame(self, fg_color="transparent")
        help_frame.grid(row=1, column=0, sticky="ew", padx=theme.PAD)
        ctk.CTkLabel(
            help_frame,
            text=("Green box over the bottom-center \"REALM - MAP\" text, cyan box over the top-left "
                  "PLAYERS / QUESTS tabs. Drag a box to move it, drag its corner to resize."),
            font=theme.FONT_SMALL, text_color=theme.ASH, anchor="w", justify="left", wraplength=820,
        ).pack(anchor="w")
        ctk.CTkLabel(
            help_frame,
            text=("The amber \"overlay\" box is the callout itself. Drag it where you want the callout "
                  "to appear (move-only, its size follows the Overlay tab)."),
            font=theme.FONT_SMALL, text_color=theme.ACCENT_BRIGHT, anchor="w", justify="left",
            wraplength=820,
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(
            help_frame,
            text="Target monitor is chosen on the Overlay tab.",
            font=theme.FONT_SMALL, text_color=theme.ASH, anchor="w",
        ).pack(anchor="w")

        self.holder = ctk.CTkFrame(self, fg_color=theme.BG_PANEL)
        self.holder.grid(row=2, column=0, sticky="nsew", padx=theme.PAD, pady=(theme.PAD, 0))
        self.holder.grid_rowconfigure(0, weight=1)
        self.holder.grid_columnconfigure(0, weight=1)

        bar = self.install_save_bar(3, self._values, self._persist)
        ctk.CTkButton(
            bar, text="Recapture screenshot", command=self._recapture,
        ).pack(side="left", padx=theme.PAD)
        ctk.CTkButton(
            bar, text="Reset to defaults", command=self._reset,
            fg_color=theme.RAISED, hover_color=theme.DANGER_HOVER,
        ).pack(side="right")

    def on_show(self):
        """(re)grab when first shown or when the Overlay tab changed the target monitor"""
        mon = int(config_bind.get(self.cfg, "overlay.monitor", 0))
        if self.canvas is None or mon != self._loaded_mon:
            self._load(mon)

    # screenshot + canvas
    def _grab(self, monitor):
        """(PIL rgb image, monitor bounds) for the target monitor, via mss with no numpy"""
        import mss
        with mss.mss() as sct:
            bounds = _monitor_bounds(monitor, sct)
            shot = sct.grab(bounds)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        return img, bounds

    def _clear_holder(self):
        for w in self.holder.winfo_children():
            w.destroy()
        self.canvas = None

    def _load(self, monitor):
        """grab the monitor, build the canvas at a fitted scale, and draw all three boxes from config"""
        self._clear_holder()
        try:
            img, bounds = self._grab(monitor)
        except Exception as e:
            ctk.CTkLabel(
                self.holder, text=f"could not grab the screen:\n{type(e).__name__}: {e}",
                text_color=theme.ASH, justify="left",
            ).grid(row=0, column=0, padx=theme.PAD, pady=theme.PAD)
            self._loaded_mon = monitor
            return

        self.bounds = bounds
        self.W, self.H = bounds["width"], bounds["height"]
        self.k = min(CANVAS_MAX_W / self.W, CANVAS_MAX_H / self.H)
        disp_w, disp_h = int(self.W * self.k), int(self.H * self.k)
        img = img.resize((disp_w, disp_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)

        self.canvas = tk.Canvas(
            self.holder, width=disp_w, height=disp_h, highlightthickness=0, bd=0, bg=theme.BG_DEEP)
        self.canvas.grid(row=0, column=0)
        self._img_item = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        self.green = _DragBox(
            self.canvas, *self._green_canvas_rect(self.cfg), GREEN, on_change=self.refresh_dirty)
        self.cyan = _DragBox(
            self.canvas, *self._cyan_canvas_rect(self.cfg), CYAN, on_change=self.refresh_dirty)
        self.overlay_box = _DragBox(
            self.canvas, *self._overlay_canvas_rect(self.cfg), theme.ACCENT_BRIGHT,
            resizable=False, label="overlay", on_change=self.refresh_dirty)
        self._loaded_mon = monitor
        self._saved = self._values()  # baseline the star against the just-loaded boxes

    def _recapture(self):
        """re-grab only the screenshot, keeping the boxes, useful after opening the scoreboard elsewhere"""
        if self.canvas is None:
            self.on_show()
            return
        try:
            img, bounds = self._grab(self._loaded_mon)
        except Exception:
            return
        if (bounds["width"], bounds["height"]) != (self.W, self.H):  # monitor changed, rebuild is honest
            self._load(self._loaded_mon)
            return
        img = img.resize((int(self.W * self.k), int(self.H * self.k)), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.itemconfigure(self._img_item, image=self._photo)

    def _reset(self):
        """restore the seeded regions and overlay corner, persist at once, then resync and clear the star"""
        if self.canvas is None:
            return
        if not messagebox.askyesno(
            "reset calibration",
            "Reset the map box, anchor box, and overlay position to their defaults? This overwrites your "
            "current calibration and saves immediately.",
        ):
            return
        seed = config_bind.seed()
        config_bind.set(self.cfg, "ocr_region", seed["ocr_region"])
        config_bind.set(self.cfg, "anchor_region", seed["anchor_region"])
        config_bind.set(self.cfg, "overlay.x", seed["overlay"]["x"])
        config_bind.set(self.cfg, "overlay.y", seed["overlay"]["y"])
        try:
            config_bind.save(self.cfg)
        except Exception as e:
            messagebox.showerror("config error", f"{type(e).__name__}: {e}")
            return
        self._resync_boxes()

    # forward math (monitor-local px, scaled to canvas by k), mirrors src.capture
    def _green_canvas_rect(self, cfg):
        o = config_bind.get(cfg, "ocr_region", {})
        w = o["width_frac"] * self.W
        x = o["center_x_frac"] * self.W - w / 2
        y = o["top_frac"] * self.H
        h = o["height_frac"] * self.H
        return (x * self.k, y * self.k, (x + w) * self.k, (y + h) * self.k)

    def _cyan_canvas_rect(self, cfg):
        a = config_bind.get(cfg, "anchor_region", {})
        s = self.H / 1440.0
        x = a["left_px_at_1440"] * s
        y = a["top_px_at_1440"] * s
        w = a["width_px_at_1440"] * s
        h = a["height_px_at_1440"] * s
        return (x * self.k, y * self.k, (x + w) * self.k, (y + h) * self.k)

    def _overlay_canvas_rect(self, cfg):
        """amber overlay-proxy rect in canvas px, a square of overlay.size scaled by k.

        overlay.x/y are absolute virtual-screen px, so subtract the monitor origin to get monitor-local px
        before scaling. an unset position falls back to the same corner OverlayWindow defaults to,
        bounds + 40.
        """
        size = int(config_bind.get(cfg, "overlay.size", 250))
        ox = config_bind.get(cfg, "overlay.x", None)
        oy = config_bind.get(cfg, "overlay.y", None)
        left, top = self.bounds["left"], self.bounds["top"]
        ax = ox if ox is not None else left + 40
        ay = oy if oy is not None else top + 40
        x0 = (ax - left) * self.k
        y0 = (ay - top) * self.k
        side = size * self.k
        return (x0, y0, x0 + side, y0 + side)

    # save-bar hooks, the base owns the dirty star and the file write
    def _values(self):
        """snapshot of the three boxes' canvas coords, None until a screenshot is loaded"""
        if self.canvas is None:
            return None
        return (self.green.coords(), self.cyan.coords(), self.overlay_box.coords())

    def _persist(self):
        """inverse the two regions back to config, map the overlay proxy to absolute overlay.x/y"""
        if self.canvas is None:
            messagebox.showinfo("nothing to save", "No screenshot is loaded to calibrate against.")
            raise SaveAbort

        gx0, gy0, gx1, gy1 = (c / self.k for c in self.green.coords())
        rw, rh = gx1 - gx0, gy1 - gy0
        config_bind.set(self.cfg, "ocr_region.center_x_frac", (gx0 + rw / 2) / self.W)
        config_bind.set(self.cfg, "ocr_region.top_frac", gy0 / self.H)
        config_bind.set(self.cfg, "ocr_region.width_frac", rw / self.W)
        config_bind.set(self.cfg, "ocr_region.height_frac", rh / self.H)

        cx0, cy0, cx1, cy1 = (c / self.k for c in self.cyan.coords())
        s = self.H / 1440.0
        config_bind.set(self.cfg, "anchor_region.left_px_at_1440", round(cx0 / s))
        config_bind.set(self.cfg, "anchor_region.top_px_at_1440", round(cy0 / s))
        config_bind.set(self.cfg, "anchor_region.width_px_at_1440", round((cx1 - cx0) / s))
        config_bind.set(self.cfg, "anchor_region.height_px_at_1440", round((cy1 - cy0) / s))

        # overlay proxy: canvas -> monitor-local px (/k), then absolute virtual-screen px (+ monitor origin)
        ox0, oy0, _, _ = (c / self.k for c in self.overlay_box.coords())
        config_bind.set(self.cfg, "overlay.x", round(self.bounds["left"] + ox0))
        config_bind.set(self.cfg, "overlay.y", round(self.bounds["top"] + oy0))

    def _after_save(self):
        """resync the boxes from the freshly-saved config so they reflect exactly what was written"""
        self._resync_boxes()

    def _resync_boxes(self):
        """redraw all three boxes from the current config and rebaseline the dirty star"""
        if self.canvas is None:
            return
        self.green.set_coords(*self._green_canvas_rect(self.cfg))
        self.cyan.set_coords(*self._cyan_canvas_rect(self.cfg))
        self.overlay_box.set_coords(*self._overlay_canvas_rect(self.cfg))
        self._saved = self._values()
        self.refresh_dirty()
