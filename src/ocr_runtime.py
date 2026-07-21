"""import tesserocr with its dlls resolved, plus the shared api cache

port of the auto-spender's ocr_runtime with the tessdata lookup and cached
PyTessBaseAPI moved in here so callout_gen and capture share one loader.
no hardcoded paths: the dll dir derives from sys.prefix (conda dev env) or
the pyinstaller bundle dir (frozen)
"""

import os
import shutil
import sys

_tess = None
_apis = {}


def _dll_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.join(sys.prefix, "Library", "bin")


def get_tesserocr():
    """import and return the tesserocr module, wiring up its dlls first

    windows gotchas this fixes:
    1. tesserocr.pyd's dlls sit in the env's Library/bin, which python 3.8+
       no longer searches via PATH, so we add it
    2. conda's libtiff links libdeflate.dll but only ships deflate.dll,
       same lib different filename, so we make the alias once
    """
    global _tess
    if _tess is None:
        d = _dll_dir()
        alias = os.path.join(d, "libdeflate.dll")
        real = os.path.join(d, "deflate.dll")
        if not os.path.exists(alias) and os.path.exists(real):
            try:
                shutil.copyfile(real, alias)
            except OSError:
                pass  # read-only install, the import below surfaces the real error
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(d)
        import tesserocr
        _tess = tesserocr
    return _tess


def tessdata_dir():
    """eng tessdata location, conda share dir in dev or the bundle dir frozen"""
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "tessdata"))
    cands += [
        os.path.join(sys.prefix, "share", "tessdata"),
        os.path.join(sys.prefix, "Library", "share", "tessdata"),
        os.environ.get("TESSDATA_PREFIX", ""),
    ]
    for p in cands:
        if p and os.path.isfile(os.path.join(p, "eng.traineddata")):
            return p
    return get_tesserocr().get_languages()[0].rstrip("/\\")


def api(psm, whitelist=None):
    """cached PyTessBaseAPI per (psm, whitelist), tesseract inits once per pair"""
    key = (psm, whitelist)
    if key not in _apis:
        t = get_tesserocr()
        a = t.PyTessBaseAPI(psm=psm, path=tessdata_dir())
        if whitelist:
            a.SetVariable("tessedit_char_whitelist", whitelist)
        _apis[key] = a
    return _apis[key]
