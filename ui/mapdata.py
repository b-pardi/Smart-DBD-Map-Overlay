"""dynamic reads over maps_index.json for the ui, with no capture or ocr pulled in.

every list is derived from the index at call time so the realm, map, and creator choices never hardcode
the game's content. the index is read as plain json guarded by paths.maps_present, never through
src.capture which would drag numpy and tesserocr into the gui exe.
"""

import json

from src import paths

ALL_REALMS = "All realms"  # realm-filter sentinel meaning every map, also the dropdown's top entry


def load_index():
    """the maps index as a plain dict, or None before the maps are downloaded or if it is unreadable"""
    if not paths.maps_present():
        return None
    try:
        with open(paths.maps_index_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def creators(index):
    """first-seen union of every overlay creator across all maps, hens pulled to the front when present"""
    seen = {}
    for m in index["maps"]:
        for ov in m["overlays"]:
            seen.setdefault(ov["creator"], None)
    names = list(seen)
    if "hens" in seen:
        names.remove("hens")
        names.insert(0, "hens")
    return names


def realms(index):
    """realm names that actually carry at least one map, in the index's declared realm order"""
    have = {m["realm"] for m in index["maps"]}
    ordered = [r["name"] for r in index.get("realms", []) if r["name"] in have]
    # keep any realm that only shows up on a map so a stale realms list never hides content
    seen = set(ordered)
    for m in index["maps"]:
        if m["realm"] not in seen:
            ordered.append(m["realm"])
            seen.add(m["realm"])
    return ordered


def maps_in(index, realm):
    """map dicts within a realm, the all-realms sentinel or an empty realm returns every map"""
    maps = index["maps"]
    if realm in ("", ALL_REALMS):
        return list(maps)
    return [m for m in maps if m["realm"] == realm]


def search(index, query, realm=ALL_REALMS):
    """maps in the realm filter whose name, realm, alt_names, or aliases contain the lowered query"""
    pool = maps_in(index, realm)
    q = query.strip().lower()
    if not q:
        return pool
    hits = []
    for m in pool:
        hay = [m["name"], m["realm"], *m.get("alt_names", []), *m.get("aliases", [])]
        if any(q in text.lower() for text in hay):
            hits.append(m)
    return hits


def labels_for(map_entry, creator):
    """ordered variation labels for a creator's overlays on the map, first-seen, empty when the creator
    has no art here"""
    seen = {}
    for ov in map_entry.get("overlays", []):
        if ov["creator"] == creator:
            seen.setdefault(ov["label"], None)
    return list(seen)


def overlay_for(map_entry, creator, label=None):
    """the overlay for creator+label, falling back to the creator's first, then the map's first, then None"""
    overlays = map_entry.get("overlays", [])
    if label is not None:
        for ov in overlays:
            if ov["creator"] == creator and ov["label"] == label:
                return ov
    for ov in overlays:
        if ov["creator"] == creator:
            return ov
    return overlays[0] if overlays else None


def map_by_name(index, name):
    """the map dict with this exact name, or None"""
    for m in index["maps"]:
        if m["name"] == name:
            return m
    return None
