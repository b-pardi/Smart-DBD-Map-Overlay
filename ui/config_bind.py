"""thin config layer for the ui so screens never touch json directly.

load/save delegate straight to src.config_io, which deep-merges the bundled seed so missing keys
backfill and the ui, the cli, and the exe never disagree on which file is authoritative. seed() hands
back a fresh default dict for a restore-defaults action. get/set walk dotted paths like
"overlay.opacity" so a screen edits a nested key without knowing the shape.
"""

import copy

from src import config_io


def load():
    """the current config, seeded on first frozen run, missing keys backfilled from the seed"""
    return config_io.load()


def save(cfg):
    """persist cfg to the resolved config path"""
    config_io.save(cfg)


def seed():
    """a fresh copy of the bundled default config, for restore-defaults"""
    return copy.deepcopy(config_io._seed())


def get(cfg, dotted, default=None):
    """value at a dotted path like "overlay.opacity", default when any step is missing"""
    cur = cfg
    for key in dotted.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def set(cfg, dotted, value):
    """set the value at a dotted path, creating intermediate dicts as needed"""
    keys = dotted.split(".")
    cur = cfg
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value
