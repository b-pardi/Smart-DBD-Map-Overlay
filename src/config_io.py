"""json config load/save, missing keys backfilled from the bundled seed

the bundled config/config.json is the key authority,
so a new build's added keys appear in an old user's config without clobbering their saved values.
"""

import copy
import json

from src import paths


def _seed():
    with open(paths.resource_path("config/config.json"), encoding="utf-8") as f:
        return json.load(f)


def _merge(base, over):
    """deep-fill from base, user values in over win where they exist"""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    seed = _seed()
    p = paths.config_path()
    if not p.exists():
        save(seed)
        return seed
    with open(p, encoding="utf-8") as f:
        user = json.load(f)
    return _merge(seed, user)


def save(cfg):
    p = paths.config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
