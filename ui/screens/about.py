"""about screen: the compass splash, the version, an update check, project links, and the credits.

the check button shares ui/updater so it reports the same way as the nav-rail one: newer offers the
releases page, current says so, an error shows itself. the credits render the attributions inline so the
artists are acknowledged right here too. the notice makes clear this is an unofficial fan project, not
affiliated with Behaviour Interactive.
"""

import webbrowser

import customtkinter as ctk

from src import paths
from src.version import GITHUB_REPO

from .. import theme, updater
from ..widgets import markdown
from ..widgets.compass import Compass
from .base import Screen

REPO_URL = f"https://github.com/{GITHUB_REPO}"
ISSUES_URL = f"{REPO_URL}/issues"


class AboutScreen(Screen):
    def __init__(self, master, app):
        super().__init__(master, app, "About")
        self.grid_rowconfigure(1, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=theme.PAD, pady=(0, theme.PAD))
        body.grid_columnconfigure(0, weight=1)

        # the heading-compass splash, the same mark the nav rail carries, larger here
        Compass(body, size=180, bg=theme.BG_PANEL).pack(pady=(theme.PAD, theme.PAD))
        ctk.CTkLabel(body, text="DBD Smart Map Overlay", font=theme.FONT_TITLE).pack()
        ctk.CTkLabel(
            body,
            text=f"version {updater.current_version()}",
            font=theme.FONT_SMALL,
            text_color=theme.ASH,
        ).pack(pady=(2, theme.PAD))

        # a centered button group, packed without fill so it sits in the middle of the body
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(pady=theme.PAD)
        self.update_btn = ctk.CTkButton(
            actions,
            text="Check for updates",
            command=lambda: updater.run_check(self.app, self.update_btn),
        )
        self.update_btn.pack(side="left")
        ctk.CTkButton(
            actions,
            text="GitHub repository",
            fg_color=theme.RAISED,
            hover_color=theme.HOVER,
            command=lambda: webbrowser.open(REPO_URL),
        ).pack(side="left", padx=theme.PAD)
        ctk.CTkButton(
            actions,
            text="Report an issue",
            fg_color=theme.RAISED,
            hover_color=theme.HOVER,
            command=lambda: webbrowser.open(ISSUES_URL),
        ).pack(side="left")

        ctk.CTkLabel(
            body,
            text=("An unofficial fan project. Not affiliated with, endorsed by, or supported by Behaviour "
                  "Interactive. Dead by Daylight and all its assets are the property of Behaviour "
                  "Interactive. Callout art belongs to its creators, credited below."),
            font=theme.FONT_SMALL,
            text_color=theme.ASH,
            anchor="w",
            justify="left",
            wraplength=640,
        ).pack(fill="x", anchor="w", padx=theme.PAD, pady=theme.PAD)

        # the artist credits, rendered inline so they live on this page too, not just the Attributions tab
        _frame, credits = self.card(body, "Credits")
        markdown.render_file(credits, paths.resource_path("attributions.md"), drop_title=True)
