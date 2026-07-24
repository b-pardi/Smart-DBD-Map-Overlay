"""instructions screen: a plain-spoken walkthrough of the overlay, rendered from markdown.

the copy is a module-level markdown string so it reads like text, not a pile of widget calls, and the
shared markdown widget turns it into themed headings and bullets in a scrollable body. voice is
deliberately casual and a little dry, still accurate to what the app actually does.
"""

import customtkinter as ctk

from .. import theme
from ..widgets import markdown
from .base import Screen

INSTRUCTIONS = """
## What this thing does

It drops a community-made callout map over your Dead by Daylight screen so you stop
squinting and guessing where shack is. That is the whole trick. It reads your screen and
shows a picture. It will not aim your skill checks for you, sadly.

## First, actually launch it

Opening this settings window does not start anything. Nothing reads your screen and no
hotkeys work until you click Launch overlay in the sidebar. That opens a console with the
logs, and the very first run downloads the callout maps. Leave that console open while you
play. Closing this settings window does not stop it.

Run the game in Windowed or Borderless. Exclusive fullscreen swallows the keypresses and
the overlay, and then nothing shows up.

## Two ways to run it

Auto mode is on by default. Open the scoreboard in a match with your Tab key and it reads
the map name off the HUD, then shows the matching callouts. You do nothing.

Manual mode is Auto switched off on the Overlay tab. You pick one map and it shows that,
every time. Good for when the read gets stubborn or you already know the map.

## Showing and hiding it

F9 is the toggle out of the box. Tap it to show the overlay, tap it again to hide. The
rest of the hotkeys live on the Controls tab, rebind them there if F-keys bother you.

One catch. Hotkey changes only take effect the next time you launch the overlay, not
mid-match, so relaunch after you rebind.

## Calibration, do it once

Auto mode only works if it reads the right slice of your screen. On the Calibration tab
drag the boxes over your HUD until the map name sits inside them. Sloppy boxes mean sloppy
reads, so do not skip this. While you are there you can drag the overlay itself somewhere
that is not sitting on top of the thing you need to see.

## Creators and variations

Different artists draw the same maps their own way. Pick whoever you like on the Overlay
tab. Variations are the separate in-game versions of a map, which is why some maps have
several and others have one. Pick the variation that matches the map you are on.

## Coming soon, the heading arrow

A facing arrow on the map that points the way you are actually looking, so you stop getting
spun around in Lery's like the rest of us. You set it up by turning in place once to mark
your facing direction. Not here yet. Soon.
"""


class InstructionsScreen(Screen):
    def __init__(self, master, app):
        super().__init__(
            master, app, "How it works", "the overlay, auto mode, hotkeys, and calibration")
        self.grid_rowconfigure(1, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=theme.PAD, pady=(0, theme.PAD))
        body.grid_columnconfigure(0, weight=1)

        markdown.render(body, INSTRUCTIONS)
