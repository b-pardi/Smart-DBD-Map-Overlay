"""repo-root vs %APPDATA% path resolution, frozen exe aware"""

import os
import sys
from pathlib import Path

APP_NAME = "smart-dbd-map-overlay"


def is_frozen():
    return getattr(sys, "frozen", False)


def resource_path(rel=""):
    """read-only bundled assets, repo root when running from source"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / rel


def user_base():
    """writable state, %APPDATA% when frozen so the install dir stays clean"""
    if is_frozen():
        return Path(os.environ["APPDATA"]) / APP_NAME
    return Path(__file__).resolve().parents[1]


def data_dir():
    return user_base() / "data"


def outlines_dir():
    return data_dir() / "outlines"


def callouts_dir():
    return data_dir() / "callouts"


def cache_dir():
    """regenerable fetch cache, safe to delete wholesale"""
    return data_dir() / ".cache"


def maps_index_path():
    return data_dir() / "maps_index.json"


def config_path():
    return user_base() / "config" / "config.json"


def ensure_user_dirs():
    for d in (data_dir(), outlines_dir(), callouts_dir(), cache_dir()):
        d.mkdir(parents=True, exist_ok=True)


def maps_present():
    """maps downloaded, the exe ships without them and fetches on first run"""
    return maps_index_path().exists()
