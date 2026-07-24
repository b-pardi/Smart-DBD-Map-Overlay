"""the nav-rail signature mark: a heading compass read like an aura through fog.

a clean compass rose, not the old cluttered map: a teal ring with cardinal ticks, a two-tone needle
whose amber half points north, and a small hub that breathes at the center. it nods at the heading-arrow
feature coming to the overlay, one honest silhouette instead of a busy floorplan.

every ring and tick is stroked twice, a wide dim halo under a thin bright core, the game's read-through
aura look. the hub and its halo pulse on a slow after-loop, three itemconfig calls a tick so it costs
nothing. colors come from the theme only.
"""

import tkinter as tk

import math

from ..theme import (
    ACCENT,
    ACCENT_BRIGHT,
    AURA_AMBER,
    AURA_TEAL,
    BONE,
    FOG_HI,
    FOG_LO,
    RAIL,
    mix,
)

PULSE_MS = 90  # slow breath, three itemconfigs a tick

R_RING = 0.42       # outer ring radius in canvas fractions
R_TICK_OUT = 0.40   # ticks stop just inside the ring
R_TICK_CARD = 0.30  # cardinal ticks reach further in than intercardinal ones
R_TICK_INTER = 0.35
NEEDLE_LEN = 0.30   # needle tip distance from center, kept inside the ring
NEEDLE_WAIST = 0.058
HUB_R = 0.052


class Compass(tk.Canvas):
    """a small self-contained compass mark, plain tk.Canvas not ctk, drawn once and breathing on a
    single after-loop. the amber needle half marks north, colors come from the theme only."""

    def __init__(self, master, size=140, bg=RAIL):
        super().__init__(master, width=size, height=size, highlightthickness=0, bd=0, bg=bg)
        self.size = size
        self._bg = bg               # halos fade to this so the mark sits on whatever it is on
        self._gw = max(2.2, size * 0.026)  # wide dim glow pass
        self._lw = max(1.0, size * 0.009)  # thin bright core pass
        self._core_dim = mix(bg, ACCENT, 0.35)
        self._phase = 0.0
        self._job = None
        self._draw()
        self._pulse()
        self.bind("<Destroy>", self._stop)

    def _xy(self, fx, fy):
        return fx * self.size, fy * self.size

    def _aura_ring(self, r_frac, color):
        """a circle stroked twice, wide dim halo under thin bright core, the aura outline look"""
        c = self.size / 2
        r = r_frac * self.size
        glow = mix(self._bg, color, 0.5)
        self.create_oval(c - r, c - r, c + r, c + r, outline=glow, width=self._gw)
        self.create_oval(c - r, c - r, c + r, c + r, outline=color, width=self._lw)

    def _tick(self, ang, r_in, color):
        """a radial tick from r_in to R_TICK_OUT at ang radians, 0 = north, clockwise"""
        c = self.size / 2
        sin, cos = math.sin(ang), -math.cos(ang)  # -cos so ang 0 points up
        x0, y0 = c + r_in * self.size * sin, c + r_in * self.size * cos
        x1, y1 = c + R_TICK_OUT * self.size * sin, c + R_TICK_OUT * self.size * cos
        self.create_line(x0, y0, x1, y1, fill=color, width=self._lw, capstyle=tk.ROUND)

    def _draw(self):
        self._fog()
        self._aura_ring(R_RING, AURA_TEAL)

        # eight ticks, cardinals reach deeper, north wears the accent so it reads without a letter
        for i in range(8):
            ang = i * math.pi / 4
            cardinal = i % 2 == 0
            r_in = R_TICK_CARD if cardinal else R_TICK_INTER
            color = AURA_AMBER if i == 0 else AURA_TEAL
            self._tick(ang, r_in, color)

        self._halo()
        self._needle()
        self._hub()

    def _fog(self):
        """a soft entity-fog bloom behind the rose, brighter toward the middle, inner disc breathes"""
        s = self.size
        cx, cy = s / 2, s / 2
        for k, col in (
            (0.58, mix(self._bg, FOG_LO, 0.55)),
            (0.40, FOG_LO),
        ):
            r = s * k
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
        r = s * 0.22
        self._bloom = self.create_oval(
            cx - r, cy - r, cx + r, cy + r, fill=mix(FOG_LO, FOG_HI, 0.4), outline="")

    def _halo(self):
        """a faint ring behind the hub that breathes, so the needle waist sits in a soft glow"""
        c = self.size / 2
        hr = self.size * HUB_R * 1.9
        self._halo_item = self.create_oval(
            c - hr, c - hr, c + hr, c + hr,
            outline=mix(self._bg, AURA_AMBER, 0.3), width=max(1.5, self.size * 0.02))

    def _needle(self):
        """a two-tone kite, amber north half over a faint bone south half, meeting at the waist"""
        c = self.size / 2
        s = self.size
        tip_n = (c, c - NEEDLE_LEN * s)
        tip_s = (c, c + NEEDLE_LEN * s)
        wl = (c - NEEDLE_WAIST * s, c)
        wr = (c + NEEDLE_WAIST * s, c)
        self.create_polygon(
            *tip_s, *wl, *wr, fill=mix(self._bg, BONE, 0.28), outline="", joinstyle=tk.ROUND)
        self.create_polygon(
            *tip_n, *wl, *wr,
            fill=AURA_AMBER, outline=mix(self._bg, AURA_AMBER, 0.5), width=self._lw,
            joinstyle=tk.ROUND)

    def _hub(self):
        """the center hub, a small filled disc that breathes with the app accent"""
        c = self.size / 2
        r = HUB_R * self.size
        self._hub_item = self.create_oval(c - r, c - r, c + r, c + r, fill=ACCENT, outline="")

    def _pulse(self):
        if not self.winfo_exists():
            return
        self._phase = (self._phase + 0.02) % 1.0
        t = (math.sin(self._phase * 2 * math.pi) + 1) / 2  # 0..1, smooth at both ends
        self.itemconfig(self._hub_item, fill=mix(self._core_dim, ACCENT_BRIGHT, t))
        self.itemconfig(self._halo_item, outline=mix(self._bg, AURA_AMBER, 0.15 + 0.5 * t))
        self.itemconfig(self._bloom, fill=mix(FOG_LO, FOG_HI, 0.3 + 0.35 * t))
        self._job = self.after(PULSE_MS, self._pulse)

    def _stop(self, _event=None):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
