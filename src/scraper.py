"""scrape pre-made callout overlays from hens333.com and allmyperks.com

realm/map names still come from the wiki's lua Module:Datatable so
the ocr matcher keeps clean names and aliases, but the map art is now the
community callout images (which actually mark shack/main) instead of the old
self-generated grid/clock overlays. each scraped image is reconciled onto a
map by name, then written to data/maps/<creator>/<Realm>/<file>
alongside data/maps_index.json
"""

import argparse
import difflib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

from src import paths

API = "https://deadbydaylight.wiki.gg/api.php"
UA = "smart-dbd-map-overlay/0.1 (contact: brandonpardi24@gmail.com)"
# hens/allmyperks sit behind cloudflare, they answer a browser ua not our bot one
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DELAY_S = 0.1

# webp store format: what both sources already ship, best size on line-art maps,
# keeps text/edges crisp and supports alpha (jpeg loses both)
TARGET_EXT = "webp"

HENS_PAGE = "https://hens333.com/callouts"
HENS_IMG_BASE = "https://hens333.com/img/dbd/callouts/"
AMP_ORIGIN = "https://allmyperks.com"
AMP_LIST = "https://allmyperks.com/maps"

# ocr text and wiki names disagree on regional spelling
SPELLING_VARIANTS = {"theatre": "theater", "centre": "center"}

# hens shorthands no fuzzy pass can bridge to the wiki map name
HENS_ALIASES = {
    "wreckers": "Wreckers' Yard",
    "haddonfield": "Lampkin Lane",
    "hawkins": "The Underground Complex",
    "ormond": "Mount Ormond Resort",
    "lerys": "Treatment Theatre",
    "midwich": "Midwich Elementary School",
    "rpd east wing": "Raccoon City Police Station East Wing",
    "rpd west wing": "Raccoon City Police Station West Wing",
}

FUZZY_CUTOFF = 0.86
_HENS_ROMAN_RE = re.compile(r"^(?P<base>.+?)\s+(?P<var>III|II|IV|VI|V)$")
_PRESCHOOL_RE = re.compile(r"^Preschool(?P<n>\d)$")
# single-variant creators drop the -N, so the number is optional
_AMP_ASSET_RE = re.compile(
    r"/assets/maps/creators/([^/]+)/([^/]+)/([^/\"&]+)\.(webp|png|jpe?g)")
_AMP_LABEL_RE = re.compile(r"-(\d+)$")

_PIL_FMT = {"webp": "WEBP", "png": "PNG", "jpg": "JPEG", "jpeg": "JPEG"}


def build_session():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _api_get(session, **params):
    params.update({"format": "json", "formatversion": 2})
    time.sleep(DELAY_S)
    r = session.get(API, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _get_text(session, url):
    """browser-ua GET for the two callout sites"""
    time.sleep(DELAY_S)
    r = session.get(url, headers={"User-Agent": BROWSER_UA}, timeout=30)
    r.raise_for_status()
    return r.text


def _cached_fetch(session, cache_name, force, fetch):
    path = paths.cache_dir() / cache_name
    if path.exists() and not force:
        return path.read_text(encoding="utf-8")
    text = fetch(session)
    path.write_text(text, encoding="utf-8")
    return text


def fetch_datatable(session, force=False):
    def fetch(s):
        data = _api_get(s, action="query", prop="revisions", titles="Module:Datatable",
                        rvprop="content", rvslots="main")
        return data["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    return _cached_fetch(session, "Datatable.lua", force, fetch)


# minimal lua table parser, covers the literal subset Module:Datatable uses
_LUA_TOKEN_RE = re.compile(r"""
    \s+ | --\[\[.*?\]\] | --[^\n]* |
    (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*') |
    (?P<num>-?\d+(?:\.\d+)?) |
    (?P<name>[A-Za-z_]\w*) |
    (?P<punct>[{}=,;])
""", re.VERBOSE | re.DOTALL)


def _lua_tokens(src):
    pos = 0
    while pos < len(src):
        m = _LUA_TOKEN_RE.match(src, pos)
        if not m:
            raise ValueError(f"lua tokenizer stuck at {src[pos:pos + 40]!r}")
        pos = m.end()
        if m.lastgroup:
            yield m.lastgroup, m.group(m.lastgroup)


def _parse_lua_value(tokens):
    kind, val = next(tokens)
    if kind == "str":
        return val[1:-1].replace('\\"', '"').replace("\\'", "'")
    if kind == "num":
        return float(val) if "." in val else int(val)
    if kind == "name":
        return {"true": True, "false": False, "nil": None}.get(val, val)
    if kind == "punct" and val == "{":
        return _parse_lua_table(tokens)
    raise ValueError(f"unexpected lua token {val!r}")


def _parse_lua_table(tokens):
    """returns a dict for keyed tables, a list for positional ones"""
    items, mapping = [], {}
    pending = None
    for kind, val in tokens:
        if kind == "punct" and val == "}":
            break
        if kind == "punct" and val in ",;":
            continue
        if kind == "punct" and val == "=":
            mapping[pending] = _parse_lua_value(tokens)
            pending = None
            continue
        if pending is not None:
            items.append(pending)
            pending = None
        if kind == "name":
            pending = val
        elif kind == "punct" and val == "{":
            items.append(_parse_lua_table(tokens))
        else:
            items.append(_parse_lua_value(iter([(kind, val)])))
    if pending is not None:
        items.append(pending)
    return mapping if mapping else items


def parse_lua_table(lua_src, varname):
    m = re.search(rf"(?m)^\s*(?:p\.)?{varname}\s*=\s*\{{", lua_src)
    if not m:
        raise ValueError(f"table {varname} not found in module source")
    tokens = _lua_tokens(lua_src[m.end():])
    table = _parse_lua_table(tokens)
    if not isinstance(table, list):
        raise ValueError(f"table {varname} parsed as {type(table).__name__}, expected list")
    return table


def normalize(text):
    """shared ocr-side name normalization, fold case, accents, punctuation"""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return " ".join(s.split())


def _key(text):
    """punctuation and space insensitive match key, folds 'azarov s' == 'azarovs'"""
    return normalize(text).replace(" ", "")


def _aliases(realm_name, map_name):
    """normalized strings the ocr matcher may see, tab hud shows 'REALM - MAP'"""
    out = [normalize(map_name), normalize(f"{realm_name} {map_name}")]
    for alias in list(out):
        for uk, us in SPELLING_VARIANTS.items():
            if uk in alias:
                out.append(alias.replace(uk, us))
    return sorted(set(out))


def build_catalog(realms, maps):
    """map records seeded from the wiki, overlays attached later"""
    realm_by_id = {r["id"]: r for r in realms}
    catalog = []
    for m in maps:
        realm = realm_by_id.get(m["realm"], {})
        alt = m.get("altName", [])
        catalog.append({
            "name": m["name"],
            "realm": realm.get("name", "Unknown"),
            "realm_abbr": realm.get("abbr", ""),
            "alt_names": alt if isinstance(alt, list) else [alt],
            "aliases": _aliases(realm.get("name", ""), m["name"]),
            "overlays": [],
        })
    return catalog


def build_matcher(catalog):
    """(key2entry, norm2entry) lookups for reconciling source names onto canon

    keys cover the map name, its alt names, and a leading-'the' stripped form so
    slugs like 'thompson-house' still reach 'The Thompson House'
    """
    key2entry, norm2entry = {}, {}
    for e in catalog:
        for nm in [e["name"], *e["alt_names"]]:
            n = normalize(nm)
            forms = {n}
            if n.startswith("the "):
                forms.add(n[4:])
            for f in forms:
                key2entry.setdefault(f.replace(" ", ""), e)
                norm2entry.setdefault(f, e)
    return key2entry, norm2entry


def match_map(src_name, matcher, alias=None):
    """entry for a source map name, exact then alias then fuzzy"""
    key2entry, norm2entry = matcher
    n = normalize(src_name)
    e = key2entry.get(n.replace(" ", ""))
    if e:
        return e
    if alias and n in alias:
        return key2entry.get(_key(alias[n]))
    hit = difflib.get_close_matches(n, list(norm2entry), n=1, cutoff=FUZZY_CUTOFF)
    return norm2entry[hit[0]] if hit else None


def _hens_variation(stem):
    """(name to match, variation label) from a hens filename stem"""
    ps = _PRESCHOOL_RE.match(stem)
    if ps:
        return "Badham Preschool", ps["n"]
    m = _HENS_ROMAN_RE.match(stem)
    if m:
        return m["base"], m["var"]
    return stem, "I"


def scrape_hens(session):
    """overlay records from hens333, one creator (Lethia), realm folder ignored"""
    html = _get_text(session, HENS_PAGE)
    records = {}
    for path in re.findall(r'data-path="([^"]+)"', html):
        fname = path.rsplit("/", 1)[-1]
        stem, _, ext = fname.rpartition(".")
        name, label = _hens_variation(stem)
        records[path] = {
            "source": "hens333", "creator": "Lethia",
            "name": name, "label": label, "ext": ext,
            "url": HENS_IMG_BASE + quote(path),
        }
    return list(records.values())


def scrape_allmyperks(session):
    """per-creator overlay records across every /maps/<slug> detail page

    map identity comes from the page slug, not the asset filename, so a stray
    thumbnail can't misfile an overlay. label is the trailing -N when present
    """
    html = _get_text(session, AMP_LIST)
    slugs = sorted(set(re.findall(r'href="/maps/([^"/]+)"', html)))
    records = {}
    for slug in tqdm(slugs, desc="allmyperks pages", unit="map"):
        page = _get_text(session, f"{AMP_ORIGIN}/maps/{slug}")
        name = slug.replace("-", " ")
        for creator, realm_slug, stem, ext in _AMP_ASSET_RE.findall(page):
            asset = f"/assets/maps/creators/{creator}/{realm_slug}/{stem}.{ext}"
            lm = _AMP_LABEL_RE.search(stem)
            records[asset] = {
                "source": "allmyperks", "creator": creator,
                "name": name, "label": lm.group(1) if lm else "1", "ext": ext,
                "url": AMP_ORIGIN + asset,
            }
    return list(records.values())


def _safe(name):
    """windows-safe filename, apostrophes are legal so keep them"""
    return re.sub(r'[<>:"/\\|?*]', "", name)


def _encode_to_target(content, src_ext):
    """image bytes in the store format, raw passthrough when already there

    keeps every frame (midwich is multi-floor) and preserves alpha, a jpeg
    target flattens alpha onto black since the format can't carry it
    """
    if src_ext.lower() == TARGET_EXT:
        return content
    import io
    from PIL import Image  # heavy, only needed when a source is not already webp
    im = Image.open(io.BytesIO(content))
    fmt = _PIL_FMT[TARGET_EXT]
    kwargs = {}
    if getattr(im, "n_frames", 1) > 1 and fmt in ("WEBP", "PNG"):
        kwargs["save_all"] = True
    if fmt == "WEBP":
        kwargs["quality"] = 95
        kwargs["lossless"] = "save_all" not in kwargs
    elif fmt == "JPEG" and (im.mode in ("RGBA", "LA") or "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (0, 0, 0))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    buf = io.BytesIO()
    im.save(buf, fmt, **kwargs)
    return buf.getvalue()


def attach_overlays(catalog, records, matcher, map_filter=None):
    """reconcile records onto canon, returns (warnings, downloads)"""
    warnings, downloads = [], []
    want = normalize(map_filter) if map_filter else None
    for r in records:
        alias = HENS_ALIASES if r["source"] == "hens333" else None
        e = match_map(r["name"], matcher, alias)
        if e is None:
            warnings.append(f"unmatched {r['source']} overlay: {r['name']} ({r['url']})")
            continue
        if want and want not in e["aliases"] and want != normalize(e["name"]):
            continue
        stem = e["name"] if r["label"] in ("I", "1") else f"{e['name']} {r['label']}"
        rel = f"maps/{_safe(r['creator'])}/{_safe(e['realm'])}/{_safe(stem)}.{TARGET_EXT}"
        e["overlays"].append({"creator": r["creator"], "source": r["source"],
                              "label": r["label"], "file": rel})
        downloads.append((r["url"], rel, r["ext"]))
    return warnings, downloads


def download_all(session, downloads, force=False):
    done = skipped = failed = converted = 0
    for url, rel, src_ext in tqdm(downloads, desc="downloading overlays", unit="img"):
        dest = paths.data_dir() / rel
        if dest.exists() and not force:
            skipped += 1
            continue
        try:
            time.sleep(DELAY_S)
            r = session.get(url, headers={"User-Agent": BROWSER_UA}, timeout=60)
            r.raise_for_status()
            data = _encode_to_target(r.content, src_ext)
        except (requests.RequestException, OSError) as ex:
            print(f"  failed {url}: {ex}")
            failed += 1
            continue
        if src_ext.lower() != TARGET_EXT:
            converted += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        done += 1
    print(f"overlays: {done} downloaded ({converted} converted to {TARGET_EXT}), "
          f"{skipped} cached, {failed} failed")


def write_index(catalog, realms, sources):
    covered = [e for e in catalog if e["overlays"]]
    index = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sources,
        "realms": [{"name": r["name"], "abbr": r.get("abbr", ""), "code_name": r.get("codeName", "")}
                   for r in realms],
        "maps": covered,
    }
    path = paths.maps_index_path()
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    n_over = sum(len(m["overlays"]) for m in covered)
    print(f"index: {len(covered)} maps, {n_over} overlays -> {path}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="scrape dbd callout overlays")
    ap.add_argument("--force", action="store_true", help="refetch cache and redownload images")
    ap.add_argument("--source", choices=["hens333", "allmyperks", "all"], default="all")
    ap.add_argument("--map", help="only attach/download overlays for this map (name, fuzzy ok)")
    ap.add_argument("--no-download", action="store_true", help="index only, skip image downloads")
    args = ap.parse_args(argv)

    paths.ensure_user_dirs()
    session = build_session()

    lua = fetch_datatable(session, force=args.force)
    realms = parse_lua_table(lua, "realms")
    maps = parse_lua_table(lua, "maps")
    catalog = build_catalog(realms, maps)
    matcher = build_matcher(catalog)
    print(f"wiki names: {len(realms)} realms, {len(maps)} maps")

    records, sources = [], []
    if args.source in ("hens333", "all"):
        records += scrape_hens(session)
        sources.append(HENS_PAGE)
    if args.source in ("allmyperks", "all"):
        records += scrape_allmyperks(session)
        sources.append(AMP_LIST)
    print(f"scraped {len(records)} overlay records")

    warnings, downloads = attach_overlays(catalog, records, matcher, map_filter=args.map)
    for w in warnings:
        print(f"  warning: {w}")

    if not args.no_download:
        download_all(session, downloads, force=args.force)
    write_index(catalog, realms, sources)

    gaps = [e["name"] for e in catalog if not e["overlays"]]
    if gaps:
        print(f"no overlays for {len(gaps)} maps: {', '.join(gaps)}")


if __name__ == "__main__":
    main()
