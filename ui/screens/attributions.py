"""attributions screen: the bundled attributions.md rendered read-only, links visible and clickable.

crediting the callout artists is a requirement of using their work, so this text ships with the app and
is shown in full. it renders through the shared markdown widget so the section structure, bold names,
and urls read as themed widgets instead of raw markup, and every url stays clickable. switching which
creator's callouts show, per map, lives on the Overlay tab.
"""

import customtkinter as ctk

from src import paths

from .. import theme
from ..widgets import markdown
from .base import Screen


class AttributionsScreen(Screen):
    def __init__(self, master, app):
        super().__init__(
            master,
            app,
            "Attributions",
            "Crediting these artists is required. Switch a map's creator on the Overlay tab.",
        )
        self.grid_rowconfigure(1, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=theme.PAD, pady=(0, theme.PAD))
        body.grid_columnconfigure(0, weight=1)

        # drop the file's own "Attributions" h1, the header already carries it
        markdown.render_file(body, paths.resource_path("attributions.md"), drop_title=True)
