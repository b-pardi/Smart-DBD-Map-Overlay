"""overlay screen: pick the map, set how the callout looks, and see a live preview of the result.

the top block chooses the map: an auto ocr toggle up top, then filters on the left (realm, map, its
in-game variation, and a search) beside a thumbnail list that takes the block's full height on the right.
the lower block sets the appearance beside a preview that re-composites the chosen overlay as the controls
move. every list is pulled from the maps index through mapdata, thumbnails stream in off the tk thread, and
all edits land on the shared config which the base Save bar persists.
"""

import customtkinter as ctk
from PIL import Image

from src import paths
from src.overlay import frame_count

from .. import config_bind, mapdata, theme, thumbnails
from .base import Screen

SIZE_MIN, SIZE_MAX = 120, 600
PREVIEW_MAX = 210  # cap the on-screen preview so the map list keeps the vertical priority
ROW_THUMB_PX = 46  # thumbnail edge for a picker row

LABEL_W = 92    # field-label column width in the appearance grid
FIELD_W = 190   # option-menu width in the appearance grid
SLIDER_W = 150
PICK_W = 230    # option-menu and search width in the map block
NO_ART = "(first available)"  # variation placeholder when the creator has no art for the map


def _hex_rgb(h):
    """"#rrggbb" -> (r, g, b), for compositing a callout onto the panel color"""
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


class OverlayScreen(Screen):
    """map selection plus appearance and a live callout preview, all editing the shared config in place"""

    def __init__(self, master, app):
        super().__init__(master, app, "Overlay", "how the callout looks and where it shows")
        self._panel_rgb = _hex_rgb(theme.BG_DEEP)  # matches the preview label so transparent areas blend
        self._preview_img = None  # keep a ref so ctk does not gc the CTkImage
        self._blank = ctk.CTkImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), size=(1, 1))
        self._ph = ctk.CTkImage(
            Image.new("RGBA", (1, 1), (0, 0, 0, 0)), size=(ROW_THUMB_PX, ROW_THUMB_PX))
        self._thumb_gen = 0   # bumps each list rebuild so stale async thumbs are dropped, never reset
        self._loader = None
        self._index_sig = None

        self.grid_rowconfigure(1, weight=1)  # the body region takes the slack
        self._build_body(mapdata.load_index())
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _build_body(self, index):
        """build every map-dependent widget from the index, re-run when the maps appear or change on us"""
        self.index = index
        self._has_maps = index is not None
        self._index_sig = self._index_sig_of(index)
        self._rows = {}       # map name -> its row button in the thumb list
        self._row_imgs = {}   # map name -> its CTkImage, kept alive against gc
        self._selected_map = config_bind.get(self.cfg, "overlay.map", "") or ""
        if self._loader is not None:
            self._loader.stop()
        self._loader = thumbnails.ThumbLoader(self) if self._has_maps else None

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.grid(row=1, column=0, sticky="nsew", padx=theme.PAD)
        self._body.grid_columnconfigure(0, weight=1)
        # the map block takes the slack but never shrinks below a usable list height
        self._body.grid_rowconfigure(0, weight=1, minsize=340)

        self._build_map_block(self._body)
        self._build_appearance_and_preview(self._body)
        self._build_hotkey_note()

        # settle the picker and appearance before seeding the save bar so nothing reads as dirty on open
        self._sync_from_selected()
        self._save_bar = self.install_save_bar(3, self._values, self._persist)

    def on_show(self):
        """rebuild the picker when the maps appeared or changed since build, eg a mid-session download"""
        index = mapdata.load_index()
        if self._index_sig_of(index) != self._index_sig:
            self._rebuild_body(index)

    def _rebuild_body(self, index):
        """drop the current body, hotkey note, and save bar, then build fresh from the new index"""
        for w in (getattr(self, "_body", None), getattr(self, "_hotkey_note", None),
                  getattr(self, "_save_bar", None)):
            if w is not None:
                w.destroy()
        self._build_body(index)

    def _index_sig_of(self, index):
        """cheap identity of the index so on_show only rebuilds when the maps really appeared or changed"""
        if index is None:
            return None
        return (index.get("generated"), len(index.get("maps", [])))

    # ---------------------------------------------------------------- block 1, map selection
    def _build_map_block(self, body):
        frame, top = self.card(
            body,
            "Map selection",
            "the map the overlay shows, or the preview target while auto mode reads it in game",
            pack=False,
        )
        frame.grid(row=0, column=0, sticky="nsew", pady=(0, theme.PAD))

        if not self._has_maps:
            self._build_auto_switch(top)
            self.auto_note.pack_configure(pady=(2, theme.PAD))
            ctk.CTkLabel(
                top,
                text=("No maps downloaded yet. Launch the overlay once to fetch them, then the map picker, "
                      "variation list, and preview fill in here."),
                font=theme.FONT_SMALL, text_color=theme.ASH,
                anchor="w", justify="left", wraplength=760,
            ).pack(fill="x", anchor="w")
            self._sync_auto_note()
            return

        # filters on the left, the search + thumbnail list on the right, split by a draggable divider
        top.pack_configure(fill="both", expand=True)
        _box, left, right = self._split(top, left_min=330, right_min=220)
        _box.pack(fill="both", expand=True)

        # auto mode, its note, and the filters share the left pane so the list reaches the block's top
        lf = ctk.CTkFrame(left, fg_color="transparent")
        lf.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD)
        self._build_auto_switch(lf)
        self.auto_note.configure(wraplength=320)
        self.auto_note.pack_configure(pady=(2, theme.PAD))

        # realm filter, drives both the map dropdown and the thumbnail list
        rf = ctk.CTkFrame(lf, fg_color="transparent")
        rf.pack(fill="x", pady=2)
        ctk.CTkLabel(rf, text="Realm", anchor="w", width=LABEL_W).pack(side="left")
        self.realm_menu = ctk.CTkOptionMenu(
            rf, width=PICK_W, values=[mapdata.ALL_REALMS, *mapdata.realms(self.index)],
            command=self._on_realm)
        self.realm_menu.pack(side="left")

        # map dropdown, the concrete selection within the realm filter
        mf = ctk.CTkFrame(lf, fg_color="transparent")
        mf.pack(fill="x", pady=2)
        ctk.CTkLabel(mf, text="Map", anchor="w", width=LABEL_W).pack(side="left")
        self.map_menu = ctk.CTkOptionMenu(mf, width=PICK_W, values=["-"], command=self._on_map_menu)
        self.map_menu.pack(side="left")

        # variation, an actual in-game variant of the map so it belongs with the map choice, not looks
        vf = ctk.CTkFrame(lf, fg_color="transparent")
        vf.pack(fill="x", pady=2)
        ctk.CTkLabel(vf, text="Variation", anchor="w", width=LABEL_W).pack(side="left")
        self.variation_menu = ctk.CTkOptionMenu(vf, width=PICK_W, values=["-"], command=self._on_variation)
        self.variation_menu.pack(side="left")

        # search sits over the list it filters, across name, realm, alt names, and aliases
        self.search_entry = ctk.CTkEntry(right, placeholder_text="search name, realm, or nickname")
        self.search_entry.pack(fill="x", padx=theme.PAD, pady=(theme.PAD, 4))
        self.search_entry.bind("<KeyRelease>", self._on_search)

        self.thumb_list = ctk.CTkScrollableFrame(right, fg_color=theme.BG_DEEP)
        self.thumb_list.pack(fill="both", expand=True, padx=theme.PAD, pady=(0, theme.PAD))
        self.thumb_list.grid_columnconfigure(0, weight=1)

        # open focused on the selected map's realm so its neighbors are the first thing shown
        sel = mapdata.map_by_name(self.index, self._selected_map) if self._selected_map else None
        self.realm_menu.set(sel["realm"] if sel else mapdata.ALL_REALMS)
        self._sync_auto_note()

    def _build_auto_switch(self, parent):
        """the auto-mode switch and its state note, built into whichever pane hosts the filters"""
        # auto mode on means ocr reads the map each match and the pick is only a live preview
        sw = ctk.CTkFrame(parent, fg_color="transparent")
        sw.pack(fill="x")
        self.auto_switch = ctk.CTkSwitch(sw, text="Auto mode (OCR)", command=self._on_auto)
        self.auto_switch.pack(side="left")
        if bool(config_bind.get(self.cfg, "overlay.auto_mode", True)):
            self.auto_switch.select()
        else:
            self.auto_switch.deselect()
        self.auto_note = ctk.CTkLabel(
            parent, text="", font=theme.FONT_SMALL, text_color=theme.ASH,
            anchor="w", justify="left", wraplength=760)
        self.auto_note.pack(fill="x", anchor="w")

    def _split(self, parent, left_min=300, right_min=220):
        """a two-pane row divided by a draggable vertical bar, centered and staying centered on resize.

        equal-weight uniform columns hold the split at the midpoint regardless of pane content, so the top
        and bottom dividers line up, and dragging the bar reweights the two sides. returns (box, left,
        right) for the caller to fill, both panes on the panel color with the bar a thin border line.
        """
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=50, uniform="pane", minsize=left_min)
        box.grid_columnconfigure(2, weight=50, uniform="pane", minsize=right_min)
        left = ctk.CTkFrame(box, fg_color=theme.BG_PANEL, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        bar = ctk.CTkFrame(box, width=5, fg_color=theme.BORDER, corner_radius=0,
                           cursor="sb_h_double_arrow")
        bar.grid(row=0, column=1, sticky="ns")
        right = ctk.CTkFrame(box, fg_color=theme.BG_PANEL, corner_radius=0)
        right.grid(row=0, column=2, sticky="nsew")

        def on_drag(e):
            frac = (bar.winfo_rootx() + e.x - box.winfo_rootx()) / max(box.winfo_width(), 1)
            frac = min(max(frac, 0.2), 0.8)
            box.grid_columnconfigure(0, weight=int(frac * 100), uniform="pane", minsize=left_min)
            box.grid_columnconfigure(2, weight=int((1 - frac) * 100), uniform="pane", minsize=right_min)
        bar.bind("<B1-Motion>", on_drag)
        return box, left, right

    def _on_auto(self):
        self._sync_auto_note()
        self.refresh_dirty()

    def _sync_auto_note(self):
        """the note under the switch, worded for the current auto state so the pick's role is never unclear"""
        hud = str(config_bind.get(self.cfg, "hud_key", "tab")).title()
        if bool(self.auto_switch.get()):
            self.auto_note.configure(
                text=(f"Auto mode reads the map from the scoreboard each match. The pick below is only a "
                      f"live preview, the real map is chosen in game when you press the menu key ({hud})."))
        else:
            self.auto_note.configure(
                text="Manual mode shows the map you pick below when you press the toggle hotkey.")

    def _current_maps(self):
        """maps under the active realm filter, ignoring the search box"""
        return mapdata.maps_in(self.index, self.realm_menu.get())

    def _refresh_map_choices(self):
        """repopulate the map dropdown from the active realm"""
        names = [m["name"] for m in self._current_maps()]
        self.map_menu.configure(values=names or ["-"])

    def _rebuild_list(self):
        """repaint the thumbnail list from the realm filter and search box, thumbs stream in async"""
        if not self._has_maps:
            return
        self._thumb_gen += 1
        gen = self._thumb_gen
        for w in self.thumb_list.winfo_children():
            w.destroy()
        self._rows.clear()
        self._row_imgs.clear()
        maps = mapdata.search(self.index, self.search_entry.get(), self.realm_menu.get())
        if not maps:
            ctk.CTkLabel(
                self.thumb_list, text="no maps match", font=theme.FONT_SMALL, text_color=theme.ASH,
            ).grid(row=0, column=0, sticky="w", padx=theme.PAD, pady=theme.PAD)
            return
        creator = self._creator_value()
        for r, m in enumerate(maps):
            btn = ctk.CTkButton(
                self.thumb_list,
                text=f"  {m['name']}    {m['realm_abbr']}",
                image=self._ph,
                height=ROW_THUMB_PX + 8,
                anchor="w",
                fg_color="transparent",
                hover_color=theme.HOVER,
                command=lambda name=m["name"]: self._select_map(name),
            )
            btn.grid(row=r, column=0, sticky="ew", padx=4, pady=1)
            self._rows[m["name"]] = btn
            self._loader.request((gen, m["name"]), m, creator, ROW_THUMB_PX, self._on_thumb_ready)
        self._highlight_selected()

    def _on_thumb_ready(self, key, im):
        """wrap a finished pil thumb into a CTkImage on the main thread, dropping stale or failed ones"""
        gen, name = key
        if gen != self._thumb_gen:
            return  # the list was rebuilt, this thumb is for an old view
        btn = self._rows.get(name)
        if btn is None or im is None:
            return
        cimg = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
        self._row_imgs[name] = cimg  # keep a ref so ctk does not gc it
        btn.configure(image=cimg)

    def _highlight_selected(self):
        for name, btn in self._rows.items():
            btn.configure(fg_color=theme.ACCENT if name == self._selected_map else "transparent")

    def _select_map(self, name, from_menu=False):
        """make name the selection, syncing the dropdown, the highlight, the variations, and the preview"""
        self._selected_map = name
        config_bind.set(self.cfg, "overlay.map", name)
        if not from_menu and name:
            self.map_menu.set(name)
        self._highlight_selected()
        self._refresh_variations()
        self._update_preview()
        self.refresh_dirty()

    def _on_map_menu(self, choice):
        self._select_map(choice, from_menu=True)

    def _on_realm(self, _v=None):
        """realm filter changed, repopulate the map dropdown and list and keep or move the selection"""
        self._refresh_map_choices()
        names = [m["name"] for m in self._current_maps()]
        if self._selected_map not in names:
            self._selected_map = names[0] if names else ""
            config_bind.set(self.cfg, "overlay.map", self._selected_map)
            if self._selected_map:
                self.map_menu.set(self._selected_map)
            self._refresh_variations()
            self._update_preview()
        else:
            self.map_menu.set(self._selected_map)
        self._rebuild_list()
        self.refresh_dirty()

    def _on_search(self, _e=None):
        self._rebuild_list()

    # ---------------------------------------------------------------- block 2, appearance + preview
    def _build_appearance_and_preview(self, body):
        # appearance and preview split by the same draggable divider, centered to line up with the map one
        box, left, right = self._split(body, left_min=300, right_min=240)
        box.grid(row=1, column=0, sticky="ew")

        ctk.CTkLabel(left, text="Appearance", font=theme.FONT_TITLE, anchor="w").pack(
            fill="x", padx=theme.PAD, pady=(theme.PAD, 2))
        a = ctk.CTkFrame(left, fg_color="transparent")
        a.pack(fill="both", expand=True, padx=theme.PAD, pady=(0, theme.PAD))
        a.grid_columnconfigure(1, weight=1)
        self._build_appearance_controls(a)

        ctk.CTkLabel(right, text="Live preview", font=theme.FONT_TITLE, anchor="w").pack(
            fill="x", padx=theme.PAD, pady=(theme.PAD, 0))
        ctk.CTkLabel(
            right, text="a real callout at the chosen size and opacity",
            font=theme.FONT_SMALL, text_color=theme.ASH, anchor="w", justify="left").pack(
            fill="x", padx=theme.PAD, pady=(0, 2))
        p = ctk.CTkFrame(right, fg_color="transparent")
        p.pack(fill="both", expand=True, padx=theme.PAD, pady=(0, theme.PAD))

        # preview centered in its pane so it reads as the focus, not pinned to a corner
        self.preview = ctk.CTkLabel(p, text="", fg_color=theme.BG_DEEP, width=PREVIEW_MAX, height=170)
        self.preview.pack(anchor="center")
        self.preview_note = ctk.CTkLabel(
            p, text="", font=theme.FONT_SMALL, text_color=theme.ASH,
            justify="center", wraplength=PREVIEW_MAX)
        self.preview_note.pack(anchor="center", pady=(4, 0))

    def _build_appearance_controls(self, a):
        # creator, no auto option, defaults to the configured creator or hens
        creators = mapdata.creators(self.index) if self._has_maps else []
        default_creator = config_bind.get(self.cfg, "overlay.creator", "hens") or "hens"
        ctk.CTkLabel(a, text="Creator", anchor="w", width=LABEL_W).grid(
            row=0, column=0, sticky="w", pady=4)
        self.creator_menu = ctk.CTkOptionMenu(
            a, width=FIELD_W, values=creators or [default_creator], command=self._on_creator)
        self.creator_menu.set(
            default_creator if (not creators or default_creator in creators) else creators[0])
        if not self._has_maps:
            self.creator_menu.configure(state="disabled")
        self.creator_menu.grid(row=0, column=1, sticky="w", pady=4)

        # opacity, matches the overlay window -alpha, live readout beside the slider
        ctk.CTkLabel(a, text="Opacity", anchor="w", width=LABEL_W).grid(
            row=1, column=0, sticky="w", pady=4)
        self.opacity = ctk.CTkSlider(
            a, from_=0.1, to=1.0, number_of_steps=18, width=SLIDER_W, command=self._on_opacity)
        self.opacity.set(float(config_bind.get(self.cfg, "overlay.opacity", 0.5)))
        self.opacity.grid(row=1, column=1, sticky="w", pady=4)
        self.opacity_val = ctk.CTkLabel(a, text="", width=40, anchor="w")
        self.opacity_val.grid(row=1, column=2, sticky="w", padx=(theme.PAD, 0))

        # size, the callout is thumbnailed to fit this many px, live readout beside the slider
        ctk.CTkLabel(a, text="Size (px)", anchor="w", width=LABEL_W).grid(
            row=2, column=0, sticky="w", pady=4)
        self.size = ctk.CTkSlider(
            a, from_=SIZE_MIN, to=SIZE_MAX, number_of_steps=(SIZE_MAX - SIZE_MIN) // 10,
            width=SLIDER_W, command=self._on_size)
        self.size.set(int(config_bind.get(self.cfg, "overlay.size", 250)))
        self.size.grid(row=2, column=1, sticky="w", pady=4)
        self.size_val = ctk.CTkLabel(a, text="", width=40, anchor="w")
        self.size_val.grid(row=2, column=2, sticky="w", padx=(theme.PAD, 0))

        # monitor, mirrors src.capture: Primary is the screen at 0,0 mapped to 0, else the mss index
        ctk.CTkLabel(a, text="Monitor", anchor="w", width=LABEL_W).grid(
            row=3, column=0, sticky="w", pady=4)
        self._mon_by_label, self._label_by_mon = self._monitor_maps()
        self.monitor_menu = ctk.CTkOptionMenu(
            a, width=FIELD_W, values=list(self._mon_by_label), command=self._on_change)
        self.monitor_menu.set(self._monitor_label(int(config_bind.get(self.cfg, "overlay.monitor", 0))))
        self.monitor_menu.grid(row=3, column=1, sticky="w", pady=4)

        self._sync_readouts()

    def _on_creator(self, _v=None):
        config_bind.set(self.cfg, "overlay.creator", self._creator_value())
        self._rebuild_list()  # thumbnails are per creator
        self._refresh_variations()
        self._update_preview()
        self.refresh_dirty()

    def _on_variation(self, _v=None):
        config_bind.set(self.cfg, "preferred_variation", self._variation_value())
        self._update_preview()
        self.refresh_dirty()

    def _on_opacity(self, _v=None):
        config_bind.set(self.cfg, "overlay.opacity", round(float(self.opacity.get()), 2))
        self._sync_readouts()
        self._update_preview()
        self.refresh_dirty()

    def _on_size(self, _v=None):
        config_bind.set(self.cfg, "overlay.size", int(round(float(self.size.get()))))
        self._sync_readouts()
        self._update_preview()
        self.refresh_dirty()

    def _on_change(self, _v=None):
        config_bind.set(self.cfg, "overlay.monitor", self._mon_by_label.get(self.monitor_menu.get(), 0))
        self.refresh_dirty()

    def _refresh_variations(self):
        """repopulate the variation menu for the selected map and creator, preselecting the saved label"""
        if not self._has_maps:
            return
        m = mapdata.map_by_name(self.index, self._selected_map)
        labels = mapdata.labels_for(m, self._creator_value()) if m else []
        if labels:
            self.variation_menu.configure(values=labels, state="normal")
            pref = config_bind.get(self.cfg, "preferred_variation", "")
            self.variation_menu.set(pref if pref in labels else labels[0])
        else:
            # the creator has no art for this map, the preview falls back and the menu shows why
            self.variation_menu.configure(values=[NO_ART], state="disabled")
            self.variation_menu.set(NO_ART)

    def _sync_readouts(self):
        self.opacity_val.configure(text=f"{float(self.opacity.get()):.2f}")
        self.size_val.configure(text=f"{int(round(float(self.size.get())))}")

    def _update_preview(self):
        """re-composite the selected overlay onto the panel color at the current opacity and size"""
        if not self._has_maps:
            self.preview.configure(image=self._blank, text="no maps downloaded")
            self.preview_note.configure(text="")
            return
        m = mapdata.map_by_name(self.index, self._selected_map)
        ov = mapdata.overlay_for(m, self._creator_value(), self._variation_value() or None) if m else None
        path = paths.data_dir() / ov["file"] if ov else None
        if not path or not path.exists():
            self.preview.configure(image=self._blank, text="callout file missing")
            self.preview_note.configure(text="")
            return

        size = min(int(round(float(self.size.get()))), PREVIEW_MAX)
        opacity = float(self.opacity.get())
        try:
            with Image.open(path) as raw:
                im = raw.convert("RGBA")
        except (OSError, ValueError):
            self.preview.configure(image=self._blank, text="could not open callout")
            self.preview_note.configure(text="")
            return
        im.thumbnail((size, size), Image.LANCZOS)  # (w, h) rgba
        # dim the whole callout by scaling its alpha, the same visual effect as the window -alpha
        alpha = im.getchannel("A").point(lambda v: int(v * opacity))  # (w, h) a
        im.putalpha(alpha)
        bg = Image.new("RGBA", im.size, self._panel_rgb + (255,))
        bg.alpha_composite(im)
        flat = bg.convert("RGB")

        self._preview_img = ctk.CTkImage(light_image=flat, dark_image=flat, size=flat.size)
        self.preview.configure(image=self._preview_img, text="")

        floors = frame_count(path)
        note = f"{ov['creator']} {ov['label']} ({ov['file'].split('/')[-1]})"
        if floors > 1:
            note += f", {floors} floors, showing floor 1"
        self.preview_note.configure(text=note)

    # ---------------------------------------------------------------- selection sync + value reads
    def _sync_from_selected(self):
        """settle the picker and appearance to the selected map, then paint the first preview"""
        if not self._has_maps:
            self._update_preview()
            return
        # clamp to a real map so the dropdowns and preview always have a target
        names = [m["name"] for m in mapdata.maps_in(self.index, mapdata.ALL_REALMS)]
        if self._selected_map not in names:
            self._selected_map = names[0] if names else ""
        self._refresh_map_choices()
        if self._selected_map:
            self.map_menu.set(self._selected_map)
        self._rebuild_list()
        self._refresh_variations()
        self._update_preview()

    def _creator_value(self):
        if not self._has_maps:
            return config_bind.get(self.cfg, "overlay.creator", "hens") or "hens"
        return self.creator_menu.get()

    def _variation_value(self):
        """the label to save as preferred_variation, empty when the menu holds no real label"""
        if not self._has_maps:
            return config_bind.get(self.cfg, "preferred_variation", "")
        v = self.variation_menu.get()
        return "" if v == NO_ART else v

    def _auto_value(self):
        return bool(self.auto_switch.get())

    # ---------------------------------------------------------------- monitor list (mirrors src.capture)
    def _monitor_maps(self):
        """(label -> config value, config value -> label) for the monitor dropdown, enumerated via mss.

        monitors[0] is the mss virtual "all screens", skipped, monitors[1:] are the real displays. Primary
        maps to config 0 (the screen at (0,0)), each real display also maps to its own mss index.
        """
        by_label = {"Primary": 0}
        by_mon = {0: "Primary"}
        try:
            import mss
            with mss.mss() as sct:
                for i, m in enumerate(sct.monitors[1:], start=1):
                    label = f"Display {i}  {m['width']}x{m['height']}"
                    by_label[label] = i
                    by_mon[i] = label
        except Exception:
            pass  # no mss / headless, Primary alone still lets the user keep the default
        return by_label, by_mon

    def _monitor_label(self, mon):
        return self._label_by_mon.get(mon, "Primary")

    # ---------------------------------------------------------------- hotkey note + save
    def _build_hotkey_note(self):
        toggle = config_bind.get(self.cfg, "hotkeys.toggle_overlay", "F9")
        self._hotkey_note = ctk.CTkLabel(
            self,
            text=(f"Press {toggle} in game to show or hide the overlay. Set hotkeys on the Controls tab."),
            font=theme.FONT_SMALL, text_color=theme.ASH, anchor="w", justify="left",
        )
        self._hotkey_note.grid(row=2, column=0, sticky="ew", padx=theme.PAD)

    def _values(self):
        """snapshot of the widgets that drive the dirty star and the save"""
        return (
            self._auto_value(),
            self._selected_map,
            self._creator_value(),
            self._variation_value(),
            round(float(self.opacity.get()), 2),
            int(round(float(self.size.get()))),
            self._mon_by_label.get(self.monitor_menu.get(), 0),
        )

    def _persist(self):
        """write every overlay setting into the shared config, the base then saves the file"""
        config_bind.set(self.cfg, "overlay.auto_mode", self._auto_value())
        config_bind.set(self.cfg, "overlay.map", self._selected_map)
        config_bind.set(self.cfg, "overlay.creator", self._creator_value())
        config_bind.set(self.cfg, "preferred_variation", self._variation_value())
        config_bind.set(self.cfg, "overlay.opacity", round(float(self.opacity.get()), 2))
        config_bind.set(self.cfg, "overlay.size", int(round(float(self.size.get()))))
        config_bind.set(self.cfg, "overlay.monitor", self._mon_by_label.get(self.monitor_menu.get(), 0))

    def _on_destroy(self, event):
        # only the screen's own teardown stops the loader, not a row button being replaced
        if event.widget is self and self._loader is not None:
            self._loader.stop()
