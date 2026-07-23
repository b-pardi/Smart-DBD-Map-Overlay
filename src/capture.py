"""screen grab + region math + ocr + map matching, one module per plan

flow on an accepted HUD press:
grab the top-left tab strip and gate on the 'PLAYERS'/'QUESTS' labels (absent means wrong menu or tabbed out, skip),
then grab the lower-center map-name box, ocr it,
and match the read against maps_index aliases (the combined 'REALM - MAP' line plus the bare map name).
strict matching only: exact-normalized then difflib 0.8,
no substring, no auto-switch on weak reads, a miss does nothing.
"""

import difflib
import json
import threading

import cv2
import mss
import numpy as np
from PIL import Image

from src import ocr_runtime, paths
from src.textnorm import normalize

_tls = threading.local()

MATCH_CUTOFF = 0.8
_MAP_UPSCALE = 4
_ANCHOR_UPSCALE = 2


def _sct():
    """thread-local mss handle, mss objects are not shareable across threads"""
    s = getattr(_tls, "sct", None)
    if s is None:
        s = _tls.sct = mss.mss()
    return s


def _psm(name):
    return getattr(ocr_runtime.get_tesserocr().PSM, name)


def load_index(path=None):
    p = path or paths.maps_index_path()
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_matcher(index):
    """(exact-alias set, alias->entry) for exact-then-fuzzy name lookup"""
    alias2entry = {}
    for e in index["maps"]:
        for a in e["aliases"]:
            alias2entry.setdefault(a, e)
    return set(alias2entry), alias2entry


# region math: anchor is edge-anchored + height-scaled px, map box is fractional
def monitor_bounds(monitor=0):
    """virtual-screen rect of the target monitor as an mss region dict

    monitor 0 means the os primary, which always sits at (0,0).
    mss orders its monitors by position not by primary, so index 1 can be the wrong screen.
    monitor >= 1 forces that mss monitor index for multi-display setups.
    """
    mons = _sct().monitors
    if monitor and 0 < monitor < len(mons):
        m = mons[monitor]
    else:
        m = next((mm for mm in mons[1:] if mm["left"] == 0 and mm["top"] == 0), mons[1])
    return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}


def anchor_region(bounds, cfg):
    scale = bounds["height"] / 1440.0
    a = cfg["anchor_region"]
    return {
        "left": bounds["left"] + round(a["left_px_at_1440"] * scale),
        "top": bounds["top"] + round(a["top_px_at_1440"] * scale),
        "width": round(a["width_px_at_1440"] * scale),
        "height": round(a["height_px_at_1440"] * scale),
    }


def map_region(bounds, cfg):
    o = cfg["ocr_region"]
    w = round(o["width_frac"] * bounds["width"])
    cx = bounds["left"] + o["center_x_frac"] * bounds["width"]
    return {
        "left": round(cx - w / 2),
        "top": bounds["top"] + round(o["top_frac"] * bounds["height"]),
        "width": w,
        "height": round(o["height_frac"] * bounds["height"]),
    }


def grab(region):
    """rgb crop of exactly this virtual-screen region"""
    raw = np.asarray(_sct().grab(region))  # (h, w, 4) bgra
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2RGB)


def crop_frame(frame_rgb, region, origin=(0, 0)):
    """subcrop a full-frame rgb array, origin = frame's virtual-screen left/top"""
    l = region["left"] - origin[0]
    t = region["top"] - origin[1]
    return frame_rgb[t:t + region["height"], l:l + region["width"]]


def preprocess(img_rgb, upscale):
    """gray, cubic upscale, otsu to black text on white for tesseract"""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    if upscale != 1:
        gray = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    _, binimg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return binimg


def _ocr(img_rgb, psm_name, upscale):
    binimg = preprocess(img_rgb, upscale)
    api = ocr_runtime.api(_psm(psm_name))
    api.SetImage(Image.fromarray(binimg))
    return api.GetUTF8Text().strip()


def anchor_present(anchor_img):
    """gate: are the tab-menu labels visible in the top-left strip"""
    n = normalize(_ocr(anchor_img, "SPARSE_TEXT", _ANCHOR_UPSCALE))
    return "players" in n or "quests" in n


def _candidates(text):
    """match strings from a read, whole first then each line

    the map box also catches the internal map-code line below the name,
    so we try each line on its own and the map-name line matches clean
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return [" ".join(lines), *lines] if lines else []


def match_name(text, matcher):
    """entry for an ocr read, exact-normalized then difflib, else None"""
    exact, alias2entry = matcher
    fuzzy = []
    for c in _candidates(text):
        n = normalize(c)
        if not n:
            continue
        if n in exact:
            return alias2entry[n]
        fuzzy.append(n)
    best, best_ratio = None, 0.0
    for n in fuzzy:
        hit = difflib.get_close_matches(n, alias2entry, n=1, cutoff=MATCH_CUTOFF)
        if hit:
            r = difflib.SequenceMatcher(None, n, hit[0]).ratio()
            if r > best_ratio:
                best, best_ratio = alias2entry[hit[0]], r
    return best


def read_and_match(map_img, matcher):
    """single-line read then sparse fallback, returns (entry_or_none, raw_text)"""
    text = _ocr(map_img, "SINGLE_LINE", _MAP_UPSCALE)
    e = match_name(text, matcher)
    if e:
        return e, text
    text2 = _ocr(map_img, "SPARSE_TEXT", _MAP_UPSCALE)
    e = match_name(text2, matcher)
    return (e, text2) if e else (None, text)


def capture_and_match(matcher, cfg, monitor=0, on_log=None, debug=False):
    """full live read: anchor gate then map-name read+match, entry or None

    a scan session retries this many times a second,
    so the anchor-absent and no-match lines are only logged under debug,
    the matched read always is
    """
    log = on_log or (lambda msg: None)
    dlog = log if debug else (lambda msg: None)
    bounds = monitor_bounds(monitor)
    if not anchor_present(grab(anchor_region(bounds, cfg))):
        dlog("skip: no PLAYERS/QUESTS anchor (wrong menu or tabbed out)")
        return None
    entry, raw = read_and_match(grab(map_region(bounds, cfg)), matcher)
    if entry:
        log(f"read {raw!r} -> {entry['realm']} - {entry['name']}")
    else:
        dlog(f"read {raw!r} -> no match")
    return entry
