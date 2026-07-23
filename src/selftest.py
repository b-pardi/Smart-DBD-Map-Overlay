"""headless build/env self-test, no game or display needed

each check returns (name, status, detail) with status pass|warn|fail|skip.
run as `python -m src.selftest`,
exits nonzero if anything failed so it can gate a release.
every real incident should earn a check here
(the region edge-anchor guard exists because fractional regions broke 16:9 in a prior app).
"""

import json
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src import capture, config_io, ocr_runtime, paths
from src.textnorm import normalize

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"

# fixtures ship at repo root, expected reference match per the tab hud text
_FIXTURES = {
    "test-screencap-1": "Withered Isle - Greenville Square",
    "test-screencap-2": "Léry's Memorial Institute - Treatment Theatre",
}


def check_writable_dirs():
    paths.ensure_user_dirs()
    probe = paths.cache_dir() / ".selftest_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return PASS, f"wrote+removed {probe.name} in {paths.cache_dir()}"


def check_config_roundtrip():
    cfg = config_io.load()
    back = json.loads(json.dumps(cfg))
    if back != cfg:
        return FAIL, "config did not survive a json round-trip"
    merged = config_io._merge({"a": 1, "b": {"x": 1}}, {"b": {"x": 2}})
    if merged != {"a": 1, "b": {"x": 2}}:
        return FAIL, f"default merge wrong: {merged}"
    return PASS, f"{len(cfg)} top-level keys, merge backfill ok"


def check_index():
    index = capture.load_index()
    maps = index.get("maps", [])
    with_overlays = [m for m in maps if m["overlays"]]
    if not with_overlays:
        return FAIL, "maps_index has no maps with overlays"
    return PASS, f"{len(maps)} maps, {len(with_overlays)} with overlays"


def check_region_edge_anchor():
    # same height, different width: the left-anchored anchor box must not move,
    # the center-anchored map box must, a revert to fractions trips this
    cfg = config_io.load()
    wide = {"left": 0, "top": 0, "width": 3440, "height": 1440}
    narrow = {"left": 0, "top": 0, "width": 2560, "height": 1440}
    a_wide, a_narrow = capture.anchor_region(wide, cfg), capture.anchor_region(narrow, cfg)
    if a_wide != a_narrow:
        return FAIL, f"anchor region drifted with width: {a_wide} vs {a_narrow}"
    if capture.map_region(wide, cfg)["left"] == capture.map_region(narrow, cfg)["left"]:
        return FAIL, "map region did not re-center with width"
    return PASS, "anchor edge-locked, map box re-centers with width"


def check_ocr():
    # a clean tesserocr import is not proof, ocr a synthetic image end to end
    try:
        ocr_runtime.get_tesserocr()
    except Exception as e:
        return WARN, f"tesserocr unavailable, machine not set up: {e}"
    img = Image.new("RGB", (500, 90), "white")
    try:
        font = ImageFont.truetype("arial.ttf", 52)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((12, 12), "COAL TOWER", fill="black", font=font)
    text = capture._ocr(np.asarray(img), "SINGLE_LINE", 2)
    if "coal tower" not in normalize(text):
        return FAIL, f"synthetic ocr read {text!r}, expected COAL TOWER"
    return PASS, f"synthetic ocr read {text.strip()!r}"


def check_fixture_reads():
    matcher = capture.build_matcher(capture.load_index())
    results = []
    for stem, want in _FIXTURES.items():
        p = paths.resource_path("fixtures") / f"{stem}.jpg"
        if not p.exists():
            return SKIP, f"fixture {stem}.jpg absent"
        frame = np.asarray(Image.open(p).convert("RGB"))
        h, w = frame.shape[:2]
        cfg = config_io.load()
        bounds = {"left": 0, "top": 0, "width": w, "height": h}
        if not capture.anchor_present(capture.crop_frame(frame, capture.anchor_region(bounds, cfg))):
            return FAIL, f"{stem}: anchor gate did not trip"
        entry, _ = capture.read_and_match(
            capture.crop_frame(frame, capture.map_region(bounds, cfg)),
            matcher
        )
        got = f"{entry['realm']} - {entry['name']}" if entry else None
        if got != want:
            return FAIL, f"{stem}: matched {got!r}, expected {want!r}"
        results.append(stem)
    return PASS, f"anchor + match ok on {', '.join(results)}"


def check_overlay_files():
    index = capture.load_index()
    files = [o["file"] for m in index["maps"] for o in m["overlays"]]
    missing = [f for f in files if not (paths.data_dir() / f).exists()]
    if not files:
        return SKIP, "no overlay files indexed"
    if missing:
        return WARN, f"{len(missing)}/{len(files)} overlay files missing, run the scraper"
    return PASS, f"all {len(files)} overlay files present on disk"


CHECKS = [
    ("writable dirs", check_writable_dirs),
    ("config round-trip", check_config_roundtrip),
    ("maps index", check_index),
    ("region edge-anchor", check_region_edge_anchor),
    ("ocr synthetic", check_ocr),
    ("fixture reads", check_fixture_reads),
    ("overlay files", check_overlay_files),
]


def run():
    results = []
    for name, fn in CHECKS:
        try:
            status, detail = fn()
        except Exception as e:  # a crashing check is itself a failure
            status, detail = FAIL, f"{type(e).__name__}: {e}"
        results.append((name, status, detail))
    return results


def main():
    results = run()
    for name, status, detail in results:
        print(f"[{status.upper():4}] {name}: {detail}")
    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    n_warn = sum(1 for _, s, _ in results if s == WARN)
    print(f"\n{len(results)} checks, {n_fail} failed, {n_warn} warnings")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
