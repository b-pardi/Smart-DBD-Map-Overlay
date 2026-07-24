"""ui palette, fonts, spacing, and two ctk draw overrides.

cosmetic only, none of this touches capture or ocr. the look is dead-by-daylight seen through fog:
warm soot charcoal surfaces, bone text, dried blood for anything destructive, and one accent hue, a
warm aura amber-gold, so the eye always knows where the app wants it. the aura motif colors (teal +
amber over a fog wash) are reserved for the compass emblem, they never tint a control. dark-only, so
every color goes into both the light and dark slots and cannot look wrong if the mode ever moves.
"""

import customtkinter as ctk
from customtkinter.windows.widgets.core_rendering import CTkCanvas

# two ctk defaults cost far more than anything we draw, set here before any widget exists

# windows defaults widget corners to font_shapes, ~10 canvas items per widget
# polygon_shapes draws the same corner as one item, identical look far cheaper
ctk.DrawEngine.preferred_drawing_method = "polygon_shapes"

# ctk scrollbar/optionmenu _draw end with update_idletasks which flushes the
# whole app tree per tick, a purely cosmetic repaint tk does next idle anyway
CTkCanvas.update_idletasks = lambda self: None


# ---------------------------------------------------------------- surfaces
# the charcoal spine, everything you read off stays here and stays quiet
BG_DEEP = "#0f0d0b"   # the window itself, the darkest thing on screen, warm cast not blue
BG_PANEL = "#191512"  # content panels, cards, entries, the callout preview

RAIL = "#141110"      # the nav rail, the app's left edge
FIELD = "#241d18"     # the surface the layout lies on, ctk's top_fg_color for nested frames
RAISED = "#33281f"    # raised controls, buttons, option menus, slider tracks
HOVER = "#43352a"     # hover on them
BORDER = "#4a3a2c"    # hairlines and unselected borders

# ---------------------------------------------------------------- accent
# aura amber-gold, the one accent, means selected or active or live wherever it shows
# deep enough that bone text sits on it comfortably
ACCENT = "#8f6824"
ACCENT_HOVER = "#a87d2e"
ACCENT_BRIGHT = "#e6c06a"  # borders, badges, links, never a text background

# ---------------------------------------------------------------- aura motif
# glowing outline colors for the compass emblem, luminous strokes over a faint fog wash
AURA_TEAL = "#4fd6c4"
AURA_AMBER = "#f0b95a"
FOG_LO = "#1a1512"  # fog wash near edge, barely above the panel
FOG_HI = "#2e2620"  # fog wash toward center

# ---------------------------------------------------------------- danger
# fresh blood, destructive only, runs hotter than the warm chrome so careful reads as different
DANGER = "#a83c37"
DANGER_HOVER = "#c04a44"

# ---------------------------------------------------------------- text
BONE = "#e8e0d4"  # primary, a warm off-white not a hard white
ASH = "#998c7e"   # secondary and hints
FOG = "#d8cbb6"   # bright neutral indicator, distinct from the amber accent it sits near


def _apply_palette():
    """repaint every ctk widget class from the surfaces above.

    what set_default_color_theme does under the hood, done in code so the frozen build ships no theme
    json to resolve. dark-only, so each color fills both the light and dark slots.
    """
    t = ctk.ThemeManager.theme

    def paint(widget, **colors):
        for key, value in colors.items():
            # "transparent" is a bare-string sentinel ctk compares directly, wrapping it in a
            # [light, dark] pair makes that check miss and hands tk an unknown color name
            t[widget][key] = value if value == "transparent" else [value, value]

    paint("CTk", fg_color=BG_DEEP)
    paint("CTkToplevel", fg_color=BG_DEEP)
    paint("CTkFrame", fg_color=BG_PANEL, top_fg_color=FIELD, border_color=BORDER)
    paint(
        "CTkButton",
        fg_color=RAISED,
        hover_color=HOVER,
        border_color=BORDER,
        text_color=BONE,
        text_color_disabled="#6b5f52",
    )
    paint("CTkLabel", text_color=BONE)
    paint(
        "CTkEntry",
        fg_color=BG_PANEL,
        border_color=BORDER,
        text_color=BONE,
        placeholder_text_color=ASH,
    )
    paint(
        "CTkCheckBox",
        fg_color=ACCENT,
        hover_color=ACCENT_HOVER,
        border_color=BORDER,
        checkmark_color=BONE,
        text_color=BONE,
        text_color_disabled="#6b5f52",
    )
    paint(
        "CTkSwitch",
        fg_color=RAISED,
        progress_color=ACCENT,
        button_color=BONE,
        button_hover_color=FOG,
        text_color=BONE,
        text_color_disabled="#6b5f52",
    )
    paint(
        "CTkSlider",
        fg_color=RAISED,
        progress_color=ACCENT,
        button_color=ACCENT_BRIGHT,
        button_hover_color=ACCENT_HOVER,
    )
    paint("CTkProgressBar", fg_color=RAISED, progress_color=ACCENT, border_color=BORDER)
    paint(
        "CTkOptionMenu",
        fg_color=RAISED,
        button_color=ACCENT,
        button_hover_color=ACCENT_HOVER,
        text_color=BONE,
        text_color_disabled="#6b5f52",
    )
    paint(
        "CTkComboBox",
        fg_color=BG_PANEL,
        border_color=BORDER,
        button_color=ACCENT,
        button_hover_color=ACCENT_HOVER,
        text_color=BONE,
        text_color_disabled="#6b5f52",
    )
    paint("CTkScrollbar", fg_color="transparent", button_color="#463b30", button_hover_color="#5d4f40")
    paint(
        "CTkSegmentedButton",
        fg_color=RAISED,
        selected_color=ACCENT,
        selected_hover_color=ACCENT_HOVER,
        unselected_color=RAISED,
        unselected_hover_color=HOVER,
        text_color=BONE,
        text_color_disabled="#6b5f52",
    )
    paint(
        "CTkTextbox",
        fg_color=BG_PANEL,
        border_color=BORDER,
        text_color=BONE,
        scrollbar_button_color="#463b30",
        scrollbar_button_hover_color="#5d4f40",
    )
    paint(
        "CTkRadioButton",
        fg_color=ACCENT,
        hover_color=ACCENT_HOVER,
        border_color=BORDER,
        text_color=BONE,
        text_color_disabled="#6b5f52",
    )
    paint("CTkScrollableFrame", label_fg_color=RAISED)
    paint("DropdownMenu", fg_color=BG_PANEL, hover_color=HOVER, text_color=BONE)


_apply_palette()


def mix(a, b, t):
    """blend two #rrggbb colors, t=0 gives a and t=1 gives b, used by the compass aura pulse"""
    ar, ag, ab = (int(a[i:i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


# ---------------------------------------------------------------- fonts and spacing
# (family, size[, style]) tuples consumed by widget font=
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_BODY = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 11)

PAD = 8
INSET = 6  # vertical breathing room a control needs so a panel has a height to round its corners
