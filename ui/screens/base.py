"""shared screen skeleton so every settings screen is built the same way.

factors the pieces the screens all repeat: the pinned title+subtitle header, the titled card, and the
dirty-aware Save bar. everything past the header is the subclass's own layout, the base just hands back
the pieces so a screen composes them where it needs (a scroll of cards, a canvas, a split panel).
"""

import tkinter.messagebox as messagebox

import customtkinter as ctk

from .. import config_bind, theme


class SaveAbort(Exception):
    """raised by a persist hook that already told the user why it stopped, so the base stays quiet"""


def card(parent, title, subtitle=None, pack=True):
    """a titled card in parent, returns (frame, body) so the caller can pack or grid the frame itself.

    body is a transparent inner frame to drop controls into, pack places the frame with the standard
    gap when the caller just wants a stacked column.
    """
    frame = ctk.CTkFrame(parent)
    if pack:
        frame.pack(fill="x", pady=(0, theme.PAD))
    ctk.CTkLabel(frame, text=title, font=theme.FONT_TITLE, anchor="w").pack(
        fill="x", anchor="w", padx=theme.PAD, pady=(theme.PAD, 0 if subtitle else 2))
    if subtitle:
        ctk.CTkLabel(
            frame, text=subtitle, font=theme.FONT_SMALL, text_color=theme.ASH,
            anchor="w", justify="left",
        ).pack(fill="x", anchor="w", padx=theme.PAD, pady=(0, 2))
    body = ctk.CTkFrame(frame, fg_color="transparent")
    body.pack(fill="x", padx=theme.PAD, pady=(0, theme.PAD))
    return frame, body


class Screen(ctk.CTkFrame):
    """base settings screen: a pinned header at row 0, plus card + a dirty-aware save bar.

    a subclass passes its title, builds its own body below the header, and where it edits config installs
    a save bar with values()/persist() hooks so the dirty star, save-error dialog, and post-save resync
    are all shared instead of copied per screen.
    """

    def __init__(self, master, app, title, subtitle=None):
        super().__init__(master)
        self.app = app
        self.cfg = app.app_state.config
        self.grid_columnconfigure(0, weight=1)
        self._values_fn = None
        self._persist_fn = None
        self._saved = None
        self._build_header(title, subtitle)

    def _build_header(self, title, subtitle):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=theme.PAD)
        ctk.CTkLabel(head, text=title, font=theme.FONT_TITLE).pack(side="left")
        if subtitle:
            ctk.CTkLabel(
                head, text=subtitle, font=theme.FONT_SMALL, text_color=theme.ASH,
            ).pack(side="left", padx=theme.PAD)

    def card(self, parent, title, subtitle=None, pack=True):
        """titled card in parent, see the module-level card(), exposed so screens use one idiom"""
        return card(parent, title, subtitle, pack)

    def install_save_bar(self, row, values_fn, persist_fn):
        """pinned save bar wired to a dirty star, returns the bar so a screen can add extra buttons.

        values_fn() -> a tuple of the current widget state, compared against the last save to drive the
        star. persist_fn() writes the widgets into self.cfg and may raise SaveAbort on bad input after
        telling the user itself. the base then saves the file and handles any write error.
        """
        self._values_fn = values_fn
        self._persist_fn = persist_fn
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", padx=theme.PAD, pady=theme.PAD)
        self.save_btn = ctk.CTkButton(bar, text="Save settings", command=self._save)
        self.save_btn.pack(side="left")
        self._saved = values_fn()
        return bar

    def refresh_dirty(self, *_):
        """flag the save button while the current state differs from the last save"""
        if self._values_fn is None or self._saved is None:
            return
        dirty = self._values_fn() != self._saved
        self.save_btn.configure(text="Save settings *" if dirty else "Save settings")

    def _save(self):
        try:
            self._persist_fn()
        except SaveAbort:
            return  # persist already surfaced the reason
        try:
            config_bind.save(self.cfg)
        except Exception as e:
            messagebox.showerror("config error", f"{type(e).__name__}: {e}")
            return
        self._saved = self._values_fn()
        self.refresh_dirty()
        self._after_save()

    def _after_save(self):
        """hook for a screen that needs to resync widgets from the freshly-saved config"""
