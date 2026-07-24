"""debug screen: a live tail of the launched overlay's console output.

the overlay runs as a separate process with its stdout and stderr teed to overlay_log_path, so this screen
just follows that file, reading whatever is new on a slow timer and appending it to a read-only box. it
never talks to the overlay, only reads its log, which keeps the two lifetimes independent.
"""

import os

import customtkinter as ctk

from src import paths

from .. import theme
from .base import Screen

POLL_MS = 400  # how often to check the log for new lines, low volume so this is plenty
MAX_CHARS = 200_000  # trim the oldest output past this so a long session never grows without bound
HINT = "Launch the overlay to see its output here.\n\nHotkey registration and every map read print below."


class DebugScreen(Screen):
    """follows the overlay log file and shows it, with clear, autoscroll, and open-folder controls"""

    def __init__(self, master, app):
        super().__init__(master, app, "Debug", "live output from the launched overlay")
        self._pos = 0          # byte offset read so far, reset when the log is truncated by a relaunch
        self._has_output = False
        self._job = None

        self.grid_rowconfigure(2, weight=1)
        self._build_toolbar()

        self.box = ctk.CTkTextbox(self, wrap="word", font=theme.FONT_MONO)
        self.box.grid(row=2, column=0, sticky="nsew", padx=theme.PAD, pady=(0, theme.PAD))
        self.box.insert("1.0", HINT)
        self.box.configure(state="disabled")

        self.bind("<Destroy>", self._on_destroy, add="+")
        self._poll()

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=theme.PAD, pady=(0, theme.PAD))
        ctk.CTkButton(bar, text="Clear", width=80, command=self._clear).pack(side="left")
        ctk.CTkButton(
            bar, text="Open log folder", width=130, fg_color=theme.RAISED,
            hover_color=theme.HOVER, command=self._open_folder).pack(side="left", padx=theme.PAD)
        self.autoscroll = ctk.CTkSwitch(bar, text="Auto-scroll")
        self.autoscroll.select()
        self.autoscroll.pack(side="right")

    def on_show(self):
        """pull anything new the moment the tab is raised, so it never looks a poll-tick stale"""
        self._pump()

    # ---------------------------------------------------------------- tail loop
    def _poll(self):
        if not self.winfo_exists():
            return
        self._pump()
        self._job = self.after(POLL_MS, self._poll)

    def _pump(self):
        """append whatever the log grew by, restarting from the top when a relaunch truncated it"""
        path = paths.overlay_log_path()
        try:
            size = path.stat().st_size
        except OSError:
            return  # no log yet, the overlay has not been launched
        if size < self._pos:  # a new launch rewrote the file, follow it from the start
            self._pos = 0
            self._reset_box()
        if size == self._pos:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
        except OSError:
            return
        if chunk:
            self._append(chunk)

    def _append(self, text):
        self.box.configure(state="normal")
        if not self._has_output:
            self.box.delete("1.0", "end")  # drop the placeholder on the first real line
            self._has_output = True
        self.box.insert("end", text)
        total = len(self.box.get("1.0", "end-1c"))
        if total > MAX_CHARS:  # keep the box bounded, trimming the oldest output
            self.box.delete("1.0", f"1.0+{total - MAX_CHARS}c")
        self.box.configure(state="disabled")
        if bool(self.autoscroll.get()):
            self.box.see("end")

    def _reset_box(self):
        self._has_output = False
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.configure(state="disabled")

    # ---------------------------------------------------------------- controls
    def _clear(self):
        """wipe the view only, the on-disk log and the read offset are left alone"""
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.configure(state="disabled")
        self._has_output = True  # a manual clear should not bring the placeholder back

    def _open_folder(self):
        paths.logs_dir().mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(paths.logs_dir())  # windows-only, the app's platform
        except Exception:
            pass

    def _on_destroy(self, event):
        if event.widget is self and self._job is not None:
            self.after_cancel(self._job)
            self._job = None
