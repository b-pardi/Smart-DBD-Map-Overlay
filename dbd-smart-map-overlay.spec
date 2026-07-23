# one-file terminal build, run from the conda env: pyinstaller dbd-smart-map-overlay.spec
# tesserocr's dlls live in the env's Library/bin, pathex lets the dep scan find them
import sys
from pathlib import Path

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

# no map art in the bundle, the app downloads it to appdata on first run,
# so the scraper and its web deps must ship too
a = Analysis(
    ["main.py"],
    pathex=[str(BIN)],
    binaries=_deflate_alias(),
    datas=[
        (str(PROJECT / "config" / "config.json"), "config"),
        (str(tessdata / "eng.traineddata"), "tessdata"),
    ],
    hiddenimports=["tesserocr", "src.version"],  # version is the update-check source of truth
    hookspath=[],
    excludes=["cv2", "customtkinter", "matplotlib", "PyQt5", "PySide6", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="dbd-smart-map-overlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # upx mangles some tesseract dlls, not worth the size win
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    icon=None,
)
