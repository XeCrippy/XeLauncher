"""Cover art for game tiles: title ID in, cached PNG out.

Two lookups, both cached to disk so a folder only ever pays for them once:

* **path → title ID**, read from the game's XEX header over xbdm (see
  :mod:`core.xex`). Exact, and works offline once cached.
* **title ID → cover**, a 64×64 PNG from Xbox Live's image host. This is the
  one part of XeLauncher that touches the internet, so it is a setting the
  user can turn off, and everything degrades to plain icons without it.

Failures are remembered as deliberately as successes. A console with two
hundred games would otherwise re-ask the network about the same missing cover
on every single repaint.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Dict, Optional, Set

from core.xex import format_title_id, read_title_id

#: The surviving Xbox Live art endpoint. The old
#: ``download.xboxlive.com/.../boxartlg.jpg`` box art path is long dead (404);
#: this one still answers with a 64×64 PNG, which is exactly a watch tile.
ART_URL = "http://image.xboxlive.com/global/t.{title_id}/icon/0/8000"

#: Big enough for any 64×64 PNG, small enough that a wrong URL cannot flood a
#: watch's storage.
MAX_ART_BYTES = 256 * 1024

REQUEST_TIMEOUT = 8.0
USER_AGENT = "XeLauncher/0.2 (Wear OS)"


def art_url(title_id: int) -> str:
    return ART_URL.format(title_id=format_title_id(title_id))


def download_art(title_id: int, timeout: float = REQUEST_TIMEOUT) -> Optional[bytes]:
    """Fetch one cover, or None if there is not one (or no internet)."""
    request = urllib.request.Request(art_url(title_id), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = response.read(MAX_ART_BYTES + 1)
    except Exception:
        # 404 for an unreleased/homebrew title, or simply no route to the
        # internet. Both mean "no art", neither is worth surfacing.
        return None

    if not data or len(data) > MAX_ART_BYTES:
        return None
    # Cheap sanity check: the endpoint serves PNG, and anything else is a
    # captive portal or an error page dressed up as a 200.
    return data if data[:8] == b"\x89PNG\r\n\x1a\n" else None


class ArtCache:
    """Disk-backed store of title IDs and covers.

    Pure bookkeeping — no threads, no Flet. The caller decides when to do the
    slow parts, which is what keeps this testable and keeps console reads on
    the one worker that is allowed to touch the socket.
    """

    IDS_FILE = "ids.json"

    def __init__(self, directory: str):
        self.directory = directory
        #: console path (lowercased) → title ID
        self._ids: Dict[str, int] = {}
        #: title IDs the art host has no cover for
        self._missing: Set[int] = set()
        #: paths whose XEX yielded no usable title ID
        self._unidentified: Set[str] = set()
        #: title ID → PNG bytes, so a repaint never re-reads the file
        self._blobs: Dict[int, bytes] = {}
        self.load()

    # ── paths ─────────────────────────────────
    def art_path(self, title_id: int) -> str:
        return os.path.join(self.directory, f"{format_title_id(title_id)}.png")

    def _index_path(self) -> str:
        return os.path.join(self.directory, self.IDS_FILE)

    # ── persistence ───────────────────────────
    def load(self):
        try:
            with open(self._index_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return
            self._ids = {
                str(k).lower(): int(v)
                for k, v in (data.get("ids") or {}).items()
                if isinstance(v, int)
            }
            self._missing = {int(v) for v in (data.get("missing") or []) if isinstance(v, int)}
            self._unidentified = {
                str(v).lower() for v in (data.get("unidentified") or []) if isinstance(v, str)
            }
        except Exception:
            # An unreadable cache costs a few network round trips, nothing more.
            pass

    def save(self) -> bool:
        try:
            os.makedirs(self.directory, exist_ok=True)
            payload = {
                "ids": self._ids,
                "missing": sorted(self._missing),
                "unidentified": sorted(self._unidentified),
            }
            temp = f"{self._index_path()}.tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            os.replace(temp, self._index_path())
            return True
        except Exception:
            return False

    def clear(self) -> bool:
        """Forget every cover and every ID."""
        self._ids.clear()
        self._missing.clear()
        self._unidentified.clear()
        self._blobs.clear()
        try:
            if os.path.isdir(self.directory):
                for name in os.listdir(self.directory):
                    if name.endswith(".png") or name == self.IDS_FILE:
                        os.remove(os.path.join(self.directory, name))
            return True
        except Exception:
            return False

    # ── lookups ───────────────────────────────
    def title_id(self, path: str) -> Optional[int]:
        return self._ids.get((path or "").lower())

    def remember_title_id(self, path: str, title_id: Optional[int]):
        key = (path or "").lower()
        if title_id:
            self._ids[key] = title_id
            self._unidentified.discard(key)
        else:
            self._unidentified.add(key)
        self.save()

    def is_hopeless(self, entry: Dict) -> bool:
        """True when nothing more can be learned about this entry.

        Either its executable had no title ID, or the art host has already said
        it has no cover for it. Asking again would just cost time on every
        repaint of the list.
        """
        path = (entry.get("path") or "").lower()
        if path in self._unidentified:
            return True
        title_id = self._ids.get(path)
        return bool(title_id and title_id in self._missing)

    def art_bytes(self, entry: Dict) -> Optional[bytes]:
        """The cover as raw bytes, ready for ``ft.Image(src=...)``.

        Flet resolves a string ``src`` against the bundled assets directory,
        which is read-only inside an APK, so a downloaded file cannot be
        referenced by path — the bytes have to travel inline. They are held in
        memory because this is called for every tile on every repaint.

        This is also why covers appear on games and not on folders: a folder
        listing can be two hundred rows, and two hundred inline images is not
        something to send a watch. Game rows are only ever a handful.
        """
        title_id = self.title_id(entry.get("path", ""))
        if not title_id:
            return None
        if title_id in self._blobs:
            return self._blobs[title_id]

        path = self.art_path(title_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as handle:
                blob = handle.read()
        except OSError:
            return None

        self._blobs[title_id] = blob
        return blob

    def cached_art(self, entry: Dict) -> Optional[str]:
        """Path to this entry's cover if it is already on disk, else None."""
        title_id = self.title_id(entry.get("path", ""))
        if not title_id:
            return None
        path = self.art_path(title_id)
        return path if os.path.isfile(path) else None

    def store_art(self, title_id: int, data: Optional[bytes]) -> Optional[str]:
        """Save a downloaded cover, or record that there is not one."""
        if not data:
            self._missing.add(title_id)
            self.save()
            return None
        try:
            os.makedirs(self.directory, exist_ok=True)
            path = self.art_path(title_id)
            temp = f"{path}.tmp"
            with open(temp, "wb") as handle:
                handle.write(data)
            os.replace(temp, path)
            self._missing.discard(title_id)
            return path
        except Exception:
            return None

    # ── the slow path ─────────────────────────
    def resolve(
        self,
        entry: Dict,
        read_range: Optional[Callable[[str, int, int], Optional[bytes]]] = None,
        fetch: Callable[[int], Optional[bytes]] = download_art,
    ) -> Optional[str]:
        """Get this entry's cover, doing whatever work is still outstanding.

        Blocking: reads the console for a title ID if it is not cached, then
        the network for the cover. Call it from a worker, never Flet's loop.
        """
        cached = self.cached_art(entry)
        if cached:
            return cached
        if self.is_hopeless(entry):
            return None

        path = entry.get("path") or ""
        title_id = self.title_id(path)

        if not title_id:
            if read_range is None:
                return None
            try:
                title_id = read_title_id(lambda offset, size: read_range(path, offset, size))
            except Exception:
                title_id = None
            self.remember_title_id(path, title_id)
            if not title_id:
                return None

        if title_id in self._missing:
            return None

        return self.store_art(title_id, fetch(title_id))
