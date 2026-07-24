# two one-file builds from one spec, run from the conda env: pyinstaller dbd-smart-map-overlay.spec
#   dbd-smart-map-overlay          the windowed gui app, bundles ui + all of src
#   dbd-smart-map-overlay-headless the lean console overlay, no ui, no customtkinter
# tesserocr's dlls live in the env's Library/bin, pathex lets the dep scan find them
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT = Path(SPECPATH)
ENV = Path(sys.prefix)
BIN = ENV / "Library" / "bin"


def _tessdata_dir():
    for c in (ENV / "share" / "tessdata", ENV / "Library" / "share" / "tessdata"):
        if (c / "eng.traineddata").is_file():
            return c
    raise SystemExit("eng.traineddata not found, activate the conda env first")


def _deflate_alias():
    # libtiff imports libdeflate.dll but conda ships deflate.dll, bundle both
    # names so ocr_runtime's runtime alias has a source
    out = []
    for name in ("deflate.dll", "libdeflate.dll"):
        p = BIN / name
        if p.is_file():
            out.append((str(p), "."))
    return out


tessdata = _tessdata_dir()

# the src chain the gui launches through, imported lazily so the dep scan needs them named
_SRC_OVERLAY = [
    "src.controller",
    "src.capture",
    "src.overlay",
    "src.scraper",
    "src.selftest",
    "src.ocr_runtime",
    "src.keywatch",
    "src.config_io",
    "src.paths",
    "src.version",
    "src.textnorm",
]

# the ui package the gui entry raises, also imported lazily behind the --run-overlay route
_UI_MODULES = [
    "ui.app",
    "ui.theme",
    "ui.config_bind",
    "ui.updater",
    "ui.launcher",
    "ui.mapdata",
    "ui.thumbnails",
    "ui.widgets.compass",
    "ui.widgets.markdown",
    "ui.screens.base",
    "ui.screens.overlay",
    "ui.screens.controls",
    "ui.screens.calibration",
    "ui.screens.instructions",
    "ui.screens.debug",
    "ui.screens.attributions",
    "ui.screens.about",
]

# no map art in the bundle, the app downloads it to appdata on first run,
# so the scraper and its web deps must ship too

# ---------------------------------------------------------------- gui app (windowed)
gui_a = Analysis(
    ["app.py"],
    pathex=[str(BIN)],
    binaries=_deflate_alias(),
    datas=[
        (str(PROJECT / "config" / "config.json"), "config"),
        (str(PROJECT / "attributions.md"), "."),
        (str(PROJECT / "ui" / "assets" / "icon.ico"), "ui/assets"),
        (str(PROJECT / "ui" / "assets" / "icon.png"), "ui/assets"),
        (str(tessdata / "eng.traineddata"), "tessdata"),
    ] + collect_data_files("customtkinter"),
    hiddenimports=["tesserocr", "customtkinter"] + _SRC_OVERLAY + _UI_MODULES,
    hookspath=[],
    excludes=["cv2", "matplotlib", "PyQt5", "PySide6", "IPython"],
    noarchive=False,
)

gui_pyz = PYZ(gui_a.pure)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.datas,
    [],
    name="dbd-smart-map-overlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # upx mangles some tesseract dlls, not worth the size win
    runtime_tmpdir=None,
    console=False,  # windowed, app.py handles the null-stdout guard
    disable_windowed_traceback=False,
    icon=str(PROJECT / "ui" / "assets" / "icon.ico"),  # the compass emblem on the exe itself
)

# ---------------------------------------------------------------- headless overlay (console)
headless_a = Analysis(
    ["main.py"],
    pathex=[str(BIN)],
    binaries=_deflate_alias(),
    datas=[
        (str(PROJECT / "config" / "config.json"), "config"),
        (str(tessdata / "eng.traineddata"), "tessdata"),
    ],
    hiddenimports=["tesserocr", "src.version"],  # version is the update-check source of truth
    hookspath=[],
    excludes=["cv2", "customtkinter", "ui", "matplotlib", "PyQt5", "PySide6", "IPython"],
    noarchive=False,
)

headless_pyz = PYZ(headless_a.pure)

headless_exe = EXE(
    headless_pyz,
    headless_a.scripts,
    headless_a.binaries,
    headless_a.datas,
    [],
    name="dbd-smart-map-overlay-headless",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # upx mangles some tesseract dlls, not worth the size win
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    icon=None,
)
