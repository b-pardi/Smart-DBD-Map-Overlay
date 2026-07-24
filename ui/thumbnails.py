"""disk-cached callout thumbnails for the map picker, generated off the tk thread.

a thumb is a small square-ish downscale of a creator's callout, cached as a png under the fetch cache so a
second visit is instant. tk is single-threaded, so ThumbLoader builds the pil image on a worker and hands
it back through the main thread for the caller to wrap into a CTkImage, which only tk-side code may touch.
"""

import hashlib
import queue
import threading

from PIL import Image

from src import paths

from . import mapdata

THUMB_PX = 64  # default square-ish edge for a picker thumb


def _cache_path(creator, file_rel, px):
    """stable png cache path for a creator's callout at a thumb size, keyed by creator, file, and px"""
    key = f"{creator}|{file_rel}|{px}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]
    return paths.cache_dir() / "thumbs" / f"{digest}.png"


def thumb_image(map_entry, creator, px=THUMB_PX):
    """a downscaled rgba pil thumb of the creator's callout for the map, cached to disk, None if missing.

    the callout is resolved via overlay_for so a creator with no art here still falls back to the map's
    first overlay, and a missing or corrupt source returns None instead of raising.
    """
    ov = mapdata.overlay_for(map_entry, creator)
    if not ov:
        return None
    cache = _cache_path(creator, ov["file"], px)
    if cache.exists():
        try:
            with Image.open(cache) as cached:
                return cached.convert("RGBA")
        except (OSError, ValueError):
            pass  # corrupt cache entry, regenerate below
    src = paths.data_dir() / ov["file"]
    if not src.exists():
        return None
    try:
        with Image.open(src) as raw:
            im = raw.convert("RGBA")
    except (OSError, ValueError):
        return None
    im.thumbnail((px, px), Image.LANCZOS)  # (w, h) rgba
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        im.save(cache, "PNG")
    except OSError:
        pass  # cache write failed, still hand back the in-memory thumb
    return im


class ThumbLoader:
    """background thumb generator that returns pil images to the tk main thread.

    a single worker drains a request queue and runs thumb_image off the main thread, dropping each result
    into a second queue that a main-thread after-loop polls, so no worker ever touches a tk widget.
    """

    POLL_MS = 40  # how often the main thread drains finished thumbs

    def __init__(self, widget):
        self._widget = widget  # any live widget, used only for after() to reach the tk main thread
        self._requests = queue.Queue()
        self._results = queue.Queue()
        self._alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._poll()

    def request(self, key, map_entry, creator, px, on_ready):
        """queue a thumb, on_ready(key, pil_or_none) fires on the main thread once it is ready"""
        self._requests.put((key, map_entry, creator, px, on_ready))

    def _run(self):
        while True:
            item = self._requests.get()
            if item is None:
                return  # sentinel from stop()
            if not self._alive:
                continue  # draining after stop, drop it
            key, map_entry, creator, px, on_ready = item
            try:
                im = thumb_image(map_entry, creator, px)
            except Exception:
                im = None
            self._results.put((on_ready, key, im))

    def _poll(self):
        """main-thread drain of finished thumbs into their callbacks, rescheduled until torn down"""
        if not self._alive:
            return
        try:
            while True:
                on_ready, key, im = self._results.get_nowait()
                try:
                    on_ready(key, im)
                except Exception:
                    pass  # callback into a row that is already gone
        except queue.Empty:
            pass
        try:
            self._widget.after(self.POLL_MS, self._poll)
        except Exception:
            self._alive = False  # widget destroyed, stop the loop

    def stop(self):
        """stop the worker and the poll loop, called from the main thread on teardown"""
        self._alive = False
        self._requests.put(None)
