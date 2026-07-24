"""controls screen: the HUD key, the six global hotkeys, and the scan-timing block.

each key field is click-to-capture: the button binds the next keypress, takes its keysym, and validates
it through keywatch.resolve_vk so an unusable key (an arrow, say) is rejected inline instead of saved.
the HUD key is watched passively and must match the in-game scoreboard key, the hotkeys go through
RegisterHotKey so F-keys are ideal and a rebind only lands on the overlay's next launch. the scan block
sits in an Advanced card. the base Screen owns the header, cards, dirty star, and save flow.
"""

import tkinter.messagebox as messagebox

import customtkinter as ctk

from src import keywatch

from .. import config_bind, theme
from .base import Screen, SaveAbort

LABEL_W = 210  # field-label column width so the value widgets line up down each group

# the six global hotkeys, config key under hotkeys.* -> field label
HOTKEYS = [
    ("toggle_overlay", "Toggle overlay"),
    ("cycle_variation", "Cycle variation"),
    ("cycle_creator", "Cycle creator"),
    ("force_read", "Force read"),
    ("move_overlay", "Move overlay"),
    ("quit", "Quit overlay"),
]

# the scan block, config key under scan.* -> (label, help, is_int)
SCAN = [
    ("post_press_delay_s", "Post-press delay (s)",
     "wait after the HUD key before the first read, lets the scoreboard start fading in", False),
    ("retry_interval_s", "Retry interval (s)",
     "gap between read attempts while the HUD finishes fading in", False),
    ("max_retries", "Max retries",
     "how many reads a single press attempts before giving up", True),
    ("rescan_cooldown_s", "Rescan cooldown (s)",
     "ignore another HUD press this soon after a scan ends, avoids double-reads", False),
]


class ControlsScreen(Screen):
    def __init__(self, master, app):
        super().__init__(master, app, "Controls", "click a key field, then press the key you want")
        self._capture = None  # (dotted, button, prev_text, funcid) while capturing a key
        self.key_btns = {}     # dotted config path -> its capture button
        self.scan_entries = {}

        # header at row 0, scrollable body at row 1, error at row 2, save bar at row 3
        self.grid_rowconfigure(1, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=theme.PAD)
        self.scroll.grid_columnconfigure(0, weight=1)

        self._build_hud()
        self._build_hotkeys()
        self._build_advanced()
        self._build_scan_entries()

        # inline validation error, shared by every key field, cleared on the next valid capture
        # kept above the save bar so it reads in place over the button, not below it
        self.error = ctk.CTkLabel(self, text="", font=theme.FONT_SMALL, text_color=theme.DANGER, anchor="w")
        self.error.grid(row=2, column=0, sticky="ew", padx=theme.PAD)

        self.install_save_bar(3, self._values, self._persist)

    def _key_field(self, parent, row, label, dotted, default):
        """a labelled click-to-capture key button bound to a dotted config path"""
        ctk.CTkLabel(parent, text=label, anchor="w", width=LABEL_W).grid(
            row=row, column=0, sticky="w", pady=4)
        btn = ctk.CTkButton(
            parent, width=120, text=str(config_bind.get(self.cfg, dotted, default)),
            command=lambda: self._capture_key(dotted, btn))
        btn.grid(row=row, column=1, sticky="w", pady=4)
        self.key_btns[dotted] = btn

    def _build_hud(self):
        _f, g = self.card(
            self.scroll, "HUD key",
            "match your in-game scoreboard key (Tab), watched passively and never taken from the game")
        self._key_field(g, 0, "Scoreboard key", "hud_key", "tab")

    def _build_hotkeys(self):
        _f, g = self.card(
            self.scroll, "Hotkeys",
            "global keys (RegisterHotKey), F-keys are ideal")
        # overlay is a separate process so a live rebind is impossible, it reads the keys at launch
        ctk.CTkLabel(
            g,
            text="Hotkey changes apply the next time you launch the overlay. Relaunch it after saving.",
            font=theme.FONT_SMALL, text_color=theme.ACCENT_BRIGHT,
            anchor="w", justify="left", wraplength=560,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        for i, (key, label) in enumerate(HOTKEYS):
            self._key_field(g, i + 1, label, f"hotkeys.{key}", "")

    def _build_advanced(self):
        _f, self.adv = self.card(
            self.scroll, "Advanced (scan timing)",
            "how a HUD press retries the read while the scoreboard fades in, defaults are fine for most")

    def _build_scan_entries(self):
        for row, (key, label, note, _is_int) in enumerate(SCAN):
            ctk.CTkLabel(self.adv, text=label, anchor="w", width=LABEL_W).grid(
                row=row, column=0, sticky="w", pady=4)
            e = ctk.CTkEntry(self.adv, width=120)
            e.insert(0, str(config_bind.get(self.cfg, f"scan.{key}", "")))
            e.grid(row=row, column=1, sticky="w", pady=4)
            e.bind("<KeyRelease>", self.refresh_dirty)
            self.scan_entries[key] = e
            ctk.CTkLabel(
                self.adv, text=note, font=theme.FONT_SMALL, text_color=theme.ASH, anchor="w",
            ).grid(row=row, column=2, sticky="w", padx=theme.PAD)

    # key capture
    def _capture_key(self, dotted, btn):
        """bind the next keypress as the key for this field, one shot, validated on the key event"""
        if self._capture is not None:
            return  # already capturing another field
        prev = btn.cget("text")
        btn.configure(text="press a key...")
        top = self.winfo_toplevel()
        funcid = top.bind("<Key>", lambda e: self._on_key(dotted, btn, e), add="+")
        self._capture = (dotted, btn, prev, funcid)
        top.focus_set()

    def _on_key(self, dotted, btn, event):
        _d, _b, prev, funcid = self._capture
        self.winfo_toplevel().unbind("<Key>", funcid)
        self._capture = None
        key = event.keysym.lower()
        if key == "escape":  # escape cancels the capture, leaving the field unchanged
            btn.configure(text=prev)
            return
        try:
            keywatch.resolve_vk(key)
        except ValueError:
            btn.configure(text=prev)
            self.error.configure(text=f"'{key}' can't be used as a key, try a letter, digit, or F-key")
            return
        self.error.configure(text="")
        config_bind.set(self.cfg, dotted, key)
        btn.configure(text=key)
        self.refresh_dirty()

    # save-bar hooks, the base owns the dirty star and the file write
    def _values(self):
        """snapshot the base compares against the last save to drive the star"""
        keys = tuple(self.key_btns[d].cget("text") for d in self.key_btns)
        scans = tuple(self.scan_entries[k].get() for k, *_ in SCAN)
        return (keys, scans)

    def _persist(self):
        """write the captured keys and the scan values, abort on a scan field that isn't a number"""
        for dotted, btn in self.key_btns.items():
            config_bind.set(self.cfg, dotted, btn.cget("text"))
        for key, label, _note, is_int in SCAN:
            raw = self.scan_entries[key].get().strip()
            try:
                config_bind.set(self.cfg, f"scan.{key}", int(raw) if is_int else float(raw))
            except ValueError:
                kind = "a whole number" if is_int else "a number"
                messagebox.showerror("invalid value", f"{label} must be {kind}.")
                raise SaveAbort
