"""Box art checks: XEX title-ID parsing, the cover cache, and the tiles."""
import struct
import sys
import tempfile
import traceback

import pathlib
SRC = str(pathlib.Path(__file__).resolve().parents[1] / "src")
sys.path.insert(0, SRC)

# ── isolation ─────────────────────────────────
# No Store may touch the user's real settings, and nothing here may reach the
# network: every download is stubbed.
import core.store as _store_module
_store_module.SRC_DIR = pathlib.Path(tempfile.mkdtemp())

from xbdm import discovery as _discovery
_discovery.find_consoles = lambda **kw: []
_discovery.local_ip = lambda: "192.168.1.5"

import flet as ft

from core import boxart, library, xex
from core.boxart import ArtCache
from ui.shell import App, SCREENS

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as ex:
        failures.append((name, traceback.format_exc()))
        print(f"  FAIL {name}: {type(ex).__name__}: {ex}")


# A 1×1 PNG — enough to be a valid cover as far as the cache is concerned.
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
       b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


def make_xex(title_id: int, exec_offset: int = 0x2900) -> bytes:
    """A synthetic XEX2 shaped like the real ones on a console."""
    data = bytearray(b"\x00" * (exec_offset + 0x20))
    data[0:4] = b"XEX2"
    entries = [(0x000002FF, 0x100), (0x00010201, 0x82000000),
               (0x00040006, exec_offset), (0x00040404, exec_offset + 0x40)]
    struct.pack_into(">I", data, 0x14, len(entries))
    for index, (key, value) in enumerate(entries):
        struct.pack_into(">II", data, 0x18 + index * 8, key, value)
    struct.pack_into(">I", data, exec_offset + 0x0C, title_id)
    return bytes(data)


def reader_for(data: bytes, log=None):
    def read(offset, size):
        if log is not None:
            log.append((offset, size))
        return data[offset:offset + size]
    return read


# ── 1. XEX parsing ────────────────────────────
print("\n[1] XEX title IDs")

def t_far_execution_info():
    """The real case: the block sits at ~0x2900, past any first read."""
    log = []
    data = make_xex(0x4D5307E6, exec_offset=0x2900)
    assert xex.read_title_id(reader_for(data, log)) == 0x4D5307E6
    print(f"       reads: {log}")
    assert len(log) == 2, "should take one header read plus one block read"
    assert log[0] == (0, xex.HEADER_READ_SIZE)
    assert log[1][1] == 0x10, "the second read must be tiny, not the whole file"
check("title ID from a far execution block", t_far_execution_info)


def t_near_execution_info_skips_a_round_trip():
    log = []
    data = make_xex(0x415607E6, exec_offset=0x100)
    assert xex.read_title_id(reader_for(data, log)) == 0x415607E6
    assert len(log) == 1, f"no second read needed: {log}"
check("a near block costs one read", t_near_execution_info_skips_a_round_trip)


def t_rejects_rubbish():
    assert xex.read_title_id(reader_for(b"NOTAXEX" + b"\x00" * 600)) is None
    assert xex.read_title_id(reader_for(b"")) is None
    assert xex.read_title_id(lambda o, s: None) is None
    # absurd header count must not send us walking off the buffer
    bad = bytearray(make_xex(0x11111111))
    struct.pack_into(">I", bad, 0x14, 100000)
    assert xex.read_title_id(reader_for(bytes(bad))) is None
    # a XEX with no execution info at all
    none = bytearray(b"\x00" * 600)
    none[0:4] = b"XEX2"
    struct.pack_into(">I", none, 0x14, 1)
    struct.pack_into(">II", none, 0x18, 0x000002FF, 0x100)
    assert xex.read_title_id(reader_for(bytes(none))) is None
check("malformed input yields None, never a crash", t_rejects_rubbish)


def t_zero_title_id():
    assert xex.read_title_id(reader_for(make_xex(0, exec_offset=0x100))) is None
    assert xex.format_title_id(0x4D5307E6) == "4D5307E6"
check("a zero title ID is not a title ID", t_zero_title_id)


# ── 2. the cache ──────────────────────────────
print("\n[2] cover cache")

ENTRY = {"name": "Halo 3", "path": "HDD:\\games\\Halo 3\\default.xex",
         "dir": "HDD:\\games\\Halo 3", "file": "default.xex"}


def t_resolve_end_to_end():
    cache = ArtCache(tempfile.mkdtemp())
    data = make_xex(0x4D5307E6)
    reads = []
    fetched = []

    def fetch(tid):
        fetched.append(tid)
        return PNG

    path = cache.resolve(
        ENTRY,
        read_range=lambda p, o, s: reader_for(data, reads)(o, s),
        fetch=fetch,
    )
    assert path and path.endswith("4D5307E6.png"), path
    assert fetched == [0x4D5307E6], fetched
    assert cache.title_id(ENTRY["path"]) == 0x4D5307E6
    blob = cache.art_bytes(ENTRY)
    assert blob == PNG, "cover bytes came back wrong"

    # second time: no console read, no download
    reads.clear(); fetched.clear()
    again = cache.resolve(ENTRY, read_range=lambda p, o, s: reader_for(data, reads)(o, s), fetch=fetch)
    assert again == path
    assert reads == [] and fetched == [], (reads, fetched)
check("resolve reads once, then serves from disk", t_resolve_end_to_end)


def t_missing_cover_is_remembered():
    cache = ArtCache(tempfile.mkdtemp())
    data = make_xex(0x99998888)
    calls = []

    def fetch(tid):
        calls.append(tid)
        return None                      # the art host has no cover

    reader = lambda p, o, s: reader_for(data)(o, s)
    assert cache.resolve(ENTRY, read_range=reader, fetch=fetch) is None
    assert calls == [0x99998888]
    assert cache.is_hopeless(ENTRY), "a known-missing cover must not be re-asked"
    assert cache.resolve(ENTRY, read_range=reader, fetch=fetch) is None
    assert calls == [0x99998888], f"asked again: {calls}"
check("a missing cover is asked for once", t_missing_cover_is_remembered)


def t_unidentifiable_is_remembered():
    cache = ArtCache(tempfile.mkdtemp())
    reads = []

    def reader(path, offset, size):
        reads.append(offset)
        return b"NOT A XEX" + b"\x00" * 500

    assert cache.resolve(ENTRY, read_range=reader, fetch=lambda t: PNG) is None
    assert cache.is_hopeless(ENTRY)
    before = len(reads)
    cache.resolve(ENTRY, read_range=reader, fetch=lambda t: PNG)
    assert len(reads) == before, "re-read a file already known to have no ID"
check("a file with no title ID is read once", t_unidentifiable_is_remembered)


def t_cache_survives_restart():
    directory = tempfile.mkdtemp()
    cache = ArtCache(directory)
    data = make_xex(0x4D5307E6)
    cache.resolve(ENTRY, read_range=lambda p, o, s: reader_for(data)(o, s), fetch=lambda t: PNG)

    fresh = ArtCache(directory)
    assert fresh.title_id(ENTRY["path"]) == 0x4D5307E6, "title ID not persisted"
    assert fresh.cached_art(ENTRY), "cover not found on disk after restart"
    assert fresh.art_bytes(ENTRY)

    assert fresh.clear()
    assert fresh.title_id(ENTRY["path"]) is None
    assert fresh.cached_art(ENTRY) is None
check("IDs and covers survive a restart, and clear works", t_cache_survives_restart)


def t_offline_is_quiet():
    """No internet must mean plain icons, not errors."""
    cache = ArtCache(tempfile.mkdtemp())
    data = make_xex(0x4D5307E6)

    def fetch(tid):
        raise OSError("Network is unreachable")

    try:
        cache.resolve(ENTRY, read_range=lambda p, o, s: reader_for(data)(o, s), fetch=fetch)
        raise AssertionError("resolve should not swallow a caller's fetch error")
    except OSError:
        pass
    # the shipped fetcher swallows it instead
    assert boxart.download_art(0x4D5307E6, timeout=0.001) is None
check("no internet degrades to no art", t_offline_is_quiet)


def t_rejects_non_png():
    import urllib.request

    class FakeResponse:
        status = 200
        def read(self, n): return b"<html>captive portal</html>"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    original = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **kw: FakeResponse()
    try:
        assert boxart.download_art(0x4D5307E6) is None, "accepted a non-PNG body"
    finally:
        urllib.request.urlopen = original
check("a captive portal is not a cover", t_rejects_non_png)


# ── 3. the app ────────────────────────────────
print("\n[3] tiles and settings")

class FakeWindow:
    width = height = 240
    resizable = True


class FakePage:
    def __init__(self, width=200):
        self.width = self.height = width
        self.overlay, self.views = [], []
        self.platform = ft.PagePlatform.ANDROID
        self.window = FakeWindow()
        self.theme = self.theme_mode = self.bgcolor = None
        self.padding = self.spacing = 0
        self.title = ""
        self.on_view_pop = self.on_resize = None
        self.tasks = []
    def update(self): pass
    def run_task(self, fn, *a, **kw): self.tasks.append(fn)


def make_app():
    app = App(FakePage())
    app.store.data_dir = lambda: tempfile.mkdtemp()
    app.store.host = "192.168.1.50"
    app.store.favorites = [dict(ENTRY)]
    app.reload_art_cache()
    app.apply_metrics()
    return app


def texts(control, out=None):
    out = [] if out is None else out
    for attr in ("value", "label"):
        value = getattr(control, attr, None)
        if isinstance(value, str) and value:
            out.append(value)
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        children = child if isinstance(child, list) else ([child] if child is not None else [])
        for c in children:
            if not isinstance(c, str):
                texts(c, out)
    return out


def find_control(control, predicate):
    if predicate(control):
        return control
    for attr in ("content", "controls", "trailing", "leading", "error_content"):
        child = getattr(control, attr, None)
        children = child if isinstance(child, list) else ([child] if child is not None else [])
        for c in children:
            if isinstance(c, str):
                continue
            found = find_control(c, predicate)
            if found is not None:
                return found
    return None


def t_tile_shows_a_cover():
    app = make_app()
    # pretend the cover is already downloaded
    app.art.remember_title_id(ENTRY["path"], 0x4D5307E6)
    app.art.store_art(0x4D5307E6, PNG)

    view = app._build("home", {})
    image = find_control(view, lambda c: isinstance(c, ft.Image))
    assert image is not None, "no cover on the pinned game"
    assert image.src == PNG, "cover bytes did not reach the tile"
    assert image.error_content is not None, "a bad cover must fall back to an icon"
check("a pinned game shows its cover", t_tile_shows_a_cover)


def t_no_cover_means_an_icon():
    app = make_app()
    view = app._build("home", {})
    assert find_control(view, lambda c: isinstance(c, ft.Image)) is None
    assert find_control(view, lambda c: getattr(c, "icon", None) == ft.Icons.SPORTS_ESPORTS)
check("no cover falls back to the icon", t_no_cover_means_an_icon)


def t_toggle_off_means_no_lookups():
    app = make_app()
    app.store.box_art = False
    assert app.art_for(ENTRY) is None
    assert not app._art_queue, "queued a lookup with box art switched off"
    app.request_art(ENTRY)
    assert not app._art_queue
check("switching box art off stops all lookups", t_toggle_off_means_no_lookups)


def t_missing_cover_is_queued_once():
    app = make_app()
    app.session.read_range = lambda p, o, s: None      # console says nothing
    for _ in range(5):
        app.art_for(ENTRY)                             # five repaints
    total = len(app._art_queue) + len(app._art_queued)
    assert len(app._art_queued) == 1, f"queued {len(app._art_queued)} times"
    assert total <= 2, total
check("repaints do not re-queue the same game", t_missing_cover_is_queued_once)


def t_settings_exposes_box_art():
    app = make_app()
    rendered = texts(app._build("settings", {}))
    assert "Box art" in rendered, rendered
    assert "Clear art cache" in rendered, rendered
    assert any("Nothing cached" in t for t in rendered), rendered
check("settings offers the toggle and a cache size", t_settings_exposes_box_art)


def t_folders_never_carry_art():
    """Folder rows must stay image-free: a 200-row listing of inline PNGs
    would be megabytes of payload for a watch."""
    app = make_app()
    client_listing = {
        "path": "HDD:\\games", "hidden": 0, "files": [],
        "folders": [{"name": f"Game {i}", "label": f"Game {i}",
                     "path": f"HDD:\\games\\Game {i}", "is_directory": True}
                    for i in range(30)],
    }
    app.browse_cache["HDD:\\games"] = client_listing
    view = app._build("browse", {"path": "HDD:\\games"})
    assert find_control(view, lambda c: isinstance(c, ft.Image)) is None
check("folder rows carry no inline images", t_folders_never_carry_art)


print("\n" + "=" * 52)
if failures:
    print(f"{len(failures)} FAILURE(S)\n")
    for name, tb in failures:
        print(f"--- {name} ---\n{tb}")
    sys.exit(1)
print("ALL CHECKS PASSED")
