"""the app shell: CTk root, left nav rail, screen switching, shared app state.

the rail carries the compass emblem, the app title, one button per screen, and pinned at its foot the
accessibility text-size control plus the Launch-overlay, Check-updates, callout-refresh, and self-test
buttons. a single AppState is built once and handed to every screen, holding the in-memory config that
all screens edit in place and each screen's Save bar persists. closing the window never kills the
overlay child, that process is a separate console meant to keep running on its own.
"""

import tkinter as tk
import tkinter.messagebox as messagebox

import customtkinter as ctk

from src import paths
from . import config_bind, launcher, theme, updater
from .widgets.compass import Compass
from .screens.overlay import OverlayScreen
from .screens.controls import ControlsScreen
from .screens.calibration import CalibrationScreen
from .screens.instructions import InstructionsScreen
from .screens.debug import DebugScreen
from .screens.attributions import AttributionsScreen
from .screens.about import AboutScreen

ASSETS = paths.resource_path("ui/assets")  # bundled read-only icons, _MEIPASS/ui/assets when frozen

# accessibility: label -> ctk widget-scaling factor, bigger text and controls app-wide
TEXT_SIZES = [
    ("Normal", 1.0),
    ("Large", 1.15),
    ("Larger", 1.3),
    ("Largest", 1.5),
]


class AppState:
    """shared in-memory state passed to every screen, mainly the one config dict.

    the config is edited in place by the screens and persisted only when a screen's Save bar runs, so
    every screen always sees the same live values. a load failure is captured as a string and surfaced
    by the ui, with the bundled seed used as a usable fallback so the window still opens.
    """

    def __init__(self):
        self.config = None
        self.config_error = None
        self.load_config()

    def load_config(self):
        try:
            self.config = config_bind.load()
            self.config_error = None
        except Exception as e:  # corrupt/unreadable config, surface it but keep the ui usable
            self.config_error = f"{type(e).__name__}: {e}"
            try:
                self.config = config_bind.seed()
            except Exception:
                self.config = {}


class App(ctk.CTk):
    NAV = [
        ("overlay", "Overlay"),
        ("controls", "Controls"),
        ("calibration", "Calibration"),
        ("instructions", "Instructions"),
        ("debug", "Debug"),
        ("attributions", "Attributions"),
        ("about", "About"),
    ]

    def __init__(self):
        self._set_app_user_model_id()  # before any window exists so the taskbar groups us right
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.app_state = AppState()
        self._apply_scale(float(config_bind.get(self.app_state.config, "ui.scale", 1.0)))
        self.title("DBD Smart Map Overlay")
        self.minsize(960, 710)
        self.geometry("1080x830")
        self._set_window_icon()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # the rail is the app's fixed-width left edge, a quieter charcoal than the content
        self.nav = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=theme.RAIL)
        self.nav.grid(row=0, column=0, sticky="nsw")
        self.nav.grid_propagate(False)  # hold the rail width regardless of button text

        self.content = ctk.CTkFrame(self, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.screens = {}
        self.nav_buttons = {}
        self._active = None
        self._build_nav()
        self._build_screens()
        self.show("overlay")

        if self.app_state.config_error:
            messagebox.showerror(
                "config error",
                f"could not load the config, using defaults:\n\n{self.app_state.config_error}\n\n"
                f"file: {paths.config_path()}",
            )

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_launch_btn()

    # window chrome
    def _set_app_user_model_id(self):
        """give windows an explicit app id so the taskbar shows our icon and groups our windows.

        windows-only, harmless elsewhere.
        """
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bpardi.dbdsmartmapoverlay")
        except Exception:
            pass

    def _set_window_icon(self):
        """set the title-bar and taskbar icon from the bundled asset if present, guarded either way.

        iconbitmap(default=) is the windows path, iconphoto the cross-platform fallback, both wrapped so
        a missing asset never blocks startup.
        """
        ico = ASSETS / "icon.ico"
        try:
            if ico.exists():
                self.iconbitmap(default=str(ico))
        except Exception:
            pass
        png = ASSETS / "icon.png"
        try:
            if png.exists():
                self._icon_img = tk.PhotoImage(file=str(png))  # keep a ref so it isn't gc'd
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def apply_child_icon(self, win):
        """stamp the app icon on a child window, re-set on a delay since ctk resets toplevel icons.

        ctk toplevels overwrite iconbitmap ~200ms after creation with the library default, so we set it
        now and again after that resettles.
        """
        ico = ASSETS / "icon.ico"
        if not ico.exists():
            return

        def stamp():
            try:
                win.iconbitmap(str(ico))
            except Exception:
                pass

        stamp()
        win.after(300, stamp)

    def _apply_scale(self, scale):
        """scale every widget and font app-wide, the accessibility text-size control"""
        try:
            ctk.set_widget_scaling(scale)
        except Exception:
            pass

    def _build_nav(self):
        # the brand mark is the heading compass, a nod at the overlay's coming heading arrow
        Compass(self.nav, size=118, bg=theme.RAIL).pack(padx=theme.PAD, pady=(theme.PAD * 2, 4))
        ctk.CTkLabel(
            self.nav,
            text="DBD Smart Map Overlay",
            font=theme.FONT_TITLE,
            wraplength=176,
            justify="center",
        ).pack(padx=theme.PAD, pady=(0, theme.PAD * 2))

        for key, label in self.NAV:
            b = ctk.CTkButton(
                self.nav,
                text=label,
                anchor="w",
                command=lambda k=key: self.show(k),
            )
            b.pack(fill="x", padx=theme.PAD, pady=4)
            self.nav_buttons[key] = b

        self._build_rail_footer()

    def _build_rail_footer(self):
        # pinned to the foot, packed bottom-first so Launch sits lowest and the rest stack above it
        self.launch_btn = ctk.CTkButton(
            self.nav,
            text="Launch overlay",
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            command=self._launch_overlay,
        )
        self.launch_btn.pack(side="bottom", fill="x", padx=theme.PAD, pady=(4, theme.PAD))
        self.update_check_btn = ctk.CTkButton(
            self.nav,
            text="Check for updates",
            command=self._check_updates,
        )
        self.update_check_btn.pack(side="bottom", fill="x", padx=theme.PAD, pady=4)
        self.callouts_btn = ctk.CTkButton(
            self.nav,
            text="Check callout updates",
            fg_color=theme.RAISED,
            hover_color=theme.HOVER,
            command=self._check_callouts,
        )
        self.callouts_btn.pack(side="bottom", fill="x", padx=theme.PAD, pady=4)
        self.selftest_btn = ctk.CTkButton(
            self.nav,
            text="\U0001f9ea  Self-test",
            fg_color=theme.RAISED,
            hover_color=theme.HOVER,
            command=self._run_selftest,
        )
        self.selftest_btn.pack(side="bottom", fill="x", padx=theme.PAD, pady=4)

        # accessibility text-size, applied live and persisted on its own so no Save bar is needed
        size = ctk.CTkFrame(self.nav, fg_color="transparent")
        size.pack(side="bottom", fill="x", padx=theme.PAD, pady=(4, 0))
        ctk.CTkLabel(size, text="Text size", font=theme.FONT_SMALL, text_color=theme.ASH).pack(
            side="left")
        self.size_menu = ctk.CTkOptionMenu(
            size, width=96, values=[lbl for lbl, _ in TEXT_SIZES], command=self._on_text_size)
        self.size_menu.set(self._size_label(float(config_bind.get(self.app_state.config, "ui.scale", 1.0))))
        self.size_menu.pack(side="right")

    def _build_screens(self):
        self.screens["overlay"] = OverlayScreen(self.content, self)
        self.screens["controls"] = ControlsScreen(self.content, self)
        self.screens["calibration"] = CalibrationScreen(self.content, self)
        self.screens["instructions"] = InstructionsScreen(self.content, self)
        self.screens["debug"] = DebugScreen(self.content, self)
        self.screens["attributions"] = AttributionsScreen(self.content, self)
        self.screens["about"] = AboutScreen(self.content, self)
        for s in self.screens.values():
            s.grid(row=0, column=0, sticky="nsew")  # stacked, show() raises one

    def show(self, key):
        """raise a screen and highlight its nav button, letting the screen resync first if it wants"""
        on_show = getattr(self.screens[key], "on_show", None)
        if callable(on_show):
            on_show()
        self.screens[key].tkraise()
        self._active = key
        for k, b in self.nav_buttons.items():
            b.configure(fg_color=theme.ACCENT if k == key else "transparent")

    # accessibility text-size
    def _size_label(self, scale):
        """the closest preset label for a stored scale, so an odd value still shows something sensible"""
        return min(TEXT_SIZES, key=lambda ls: abs(ls[1] - scale))[0]

    def _on_text_size(self, label):
        scale = dict(TEXT_SIZES).get(label, 1.0)
        self._apply_scale(scale)
        # persist only the scale on top of the on-disk config, so pending screen edits are not flushed
        try:
            disk = config_bind.load()
        except Exception:
            disk = self.app_state.config
        config_bind.set(disk, "ui.scale", scale)
        config_bind.set(self.app_state.config, "ui.scale", scale)
        try:
            config_bind.save(disk)
        except Exception as e:
            messagebox.showerror("config error", f"{type(e).__name__}: {e}")

    # overlay process
    def _launch_overlay(self):
        """spawn the overlay in its own console, guarded against a double-launch by the launcher"""
        launcher.launch_overlay()
        self._refresh_launch_btn()

    def _refresh_launch_btn(self):
        """reflect whether our overlay child is alive, polled so it re-enables when that console closes"""
        running = launcher.is_running()
        self.launch_btn.configure(
            text="Overlay running" if running else "Launch overlay",
            state="disabled" if running else "normal",
        )
        self.after(1000, self._refresh_launch_btn)

    # callout refresh (scraper)
    def _check_callouts(self):
        """refresh the callout art in a console, on the user's ok since it hits the network"""
        if not messagebox.askyesno(
            "check callout updates",
            "Fetch the latest callout maps from hens333.com and allmyperks.com?\n\n"
            "This opens a console and downloads any new or changed art (about 25 MB the first time).",
        ):
            return
        launcher.run_scraper()

    # self-test
    def _run_selftest(self):
        """run the headless self-test off-thread and show its results in a window"""
        self.selftest_btn.configure(state="disabled", text="Testing...")
        launcher.run_selftest(self, self._on_selftest_done)

    def _on_selftest_done(self, text, ok):
        self.selftest_btn.configure(state="normal", text="\U0001f9ea  Self-test")
        self._show_selftest_results(text, ok)

    def _show_selftest_results(self, text, ok):
        win = ctk.CTkToplevel(self)
        win.title("Self-test results")
        win.geometry("640x460")
        win.transient(self)
        self.apply_child_icon(win)
        head = "all checks passed" if ok else "some checks failed, see below"
        ctk.CTkLabel(
            win, text=head, font=theme.FONT_TITLE,
            text_color=theme.BONE if ok else theme.DANGER,
        ).pack(anchor="w", padx=theme.PAD, pady=theme.PAD)
        box = ctk.CTkTextbox(win, wrap="word", font=theme.FONT_MONO)
        box.pack(fill="both", expand=True, padx=theme.PAD, pady=(0, theme.PAD))
        box.insert("1.0", text or "no output")
        box.configure(state="disabled")

    # app self-update
    def _check_updates(self):
        """manual check, shared flow gives feedback and opens the releases page when newer exists"""
        updater.run_check(self, self.update_check_btn)

    def _on_close(self):
        """tear down the window only, the overlay child is a separate process and keeps running"""
        self.destroy()


def run():
    App().mainloop()
