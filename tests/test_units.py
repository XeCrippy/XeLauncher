"""Unit checks: protocol parsing, labelling, directory listing, storage, screens."""
import sys
import tempfile
import traceback

import pathlib
SRC = str(pathlib.Path(__file__).resolve().parents[1] / "src")
sys.path.insert(0, SRC)

# ── isolation ─────────────────────────────────
# Redirect every Store to a throwaway directory and stub the subnet sweep
# BEFORE anything imports them. Without this, `shell.main()` builds a real
# Store and a real discovery thread: the suite would sweep the LAN and
# overwrite the user's saved console and favourites.
import core.store as _store_module
_store_module.SRC_DIR = pathlib.Path(tempfile.mkdtemp())

from xbdm import discovery as _discovery
_discovery.find_consoles = lambda **kw: []
_discovery.local_ip = lambda: "192.168.1.5"

import flet as ft

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as ex:
        failures.append((name, traceback.format_exc()))
        print(f"  FAIL {name}: {type(ex).__name__}: {ex}")


# ── 1. imports ────────────────────────────────
print("\n[1] imports")
from core import library
from core.session import Session
from core.store import Store
from core.titles import label_for, title_name, variant_label
from core.version import APP_VERSION, _pyproject_version
from ui import actions, widgets as w
from ui.shell import App, SCREENS
from ui.theme import metrics_for
from xbdm import XbdmClient, XbdmError
from xbdm.protocol import parse_response_line
from xbdm.exceptions import XbdmCommandError
print("  ok   all modules import")
assert list(SCREENS) == ["connect", "home", "browse", "console", "settings"], list(SCREENS)
assert APP_VERSION == _pyproject_version(), (APP_VERSION, _pyproject_version())


# ── 2. protocol ───────────────────────────────
print("\n[2] protocol")
def t_protocol():
    assert parse_response_line(b"200- OK\r\n").ok
    assert parse_response_line(b"202- multiline response follows\r\n").multiline
    try:
        parse_response_line(b"402- file not found\r\n")
        raise AssertionError("should have raised")
    except XbdmCommandError as ex:
        assert ex.code == 402
        assert "no longer on the console" in ex.friendly, ex.friendly
check("parse 200/202/402", t_protocol)


# ── 3. labelling ──────────────────────────────
print("\n[3] titles")
def t_labels():
    cases = [
        ((r"HDD:\games\Halo 3", "default.xex"), "Halo 3"),
        ((r"HDD:\games\Halo.3.NTSC", "default.xex"), "Halo 3 NTSC"),
        ((r"HDD:\games\Saints Row 2 [USA]", "default.xex"), "Saints Row 2"),
        ((r"USB0:\games\Call of Duty", "default_mp.xex"), "Call of Duty — Multiplayer"),
        ((r"HDD:\Content\0000\4D5307E6", "default.xex"), "Halo 3"),
    ]
    for (directory, filename), expected in cases:
        got = label_for(directory, filename)
        print(f"       {directory}\\{filename} -> {got!r}")
        assert got == expected, f"wanted {expected!r}, got {got!r}"
check("label_for", t_labels)


def t_variants():
    cases = {"default.xex": "Campaign", "default_mp.xex": "Multiplayer",
             "defaultmp.xex": "Multiplayer", "default_sp.xex": "Campaign",
             "default_zm.xex": "Zombies", "default_mp2.xex": "MP2",
             "modloader.xex": "modloader"}
    for filename, expected in cases.items():
        assert variant_label(filename) == expected, (filename, variant_label(filename))
check("variant labels", t_variants)


def t_folder_labels():
    # a title-ID folder resolves to the game; anything else is left alone
    assert library.folder_label("4D5307E6") == "Halo 3", library.folder_label("4D5307E6")
    assert library.folder_label("games") == "games"
    assert title_name("notahexid") is None
check("folder labels resolve title IDs", t_folder_labels)


# ── 4. directory listing ──────────────────────
print("\n[4] browsing a folder")

FS = {
    "HDD:\\": [
        {"name": "games", "is_directory": True},
        {"name": "Content", "is_directory": True},
        {"name": "readme.txt", "is_directory": False},
        {"name": "xshell.xex", "is_directory": False, "size": 4096},
    ],
    "HDD:\\games": [
        {"name": "Call of Duty Black Ops", "is_directory": True},
        {"name": "Halo 3", "is_directory": True},
    ],
    "HDD:\\games\\Call of Duty Black Ops": [
        {"name": "default.xex", "is_directory": False, "size": 100},
        {"name": "default_mp.xex", "is_directory": False, "size": 200},
        {"name": "installer.exe", "is_directory": False, "size": 300},
        {"name": "game.iso", "is_directory": False},
        {"name": "readme.txt", "is_directory": False},
        {"name": "Media", "is_directory": True},
    ],
    "HDD:\\games\\Halo 3": [{"name": "default.xex", "is_directory": False}],
    "HDD:\\Content": [{"name": "4D5307E6", "is_directory": True}],
    "HDD:\\nothing": [{"name": "a.iso", "is_directory": False},
                      {"name": "b.bin", "is_directory": False}],
}


class FakeClient:
    def __init__(self):
        self.reads = []
    def get_drive_list(self):
        return ["HDD:\\", "USB0:\\"]
    def get_directory_contents(self, path):
        self.reads.append(path)
        return FS.get(path, [])


def t_listing_filters():
    listing = library.list_directory(FakeClient(), "HDD:\\games\\Call of Duty Black Ops")
    files = [f["file"] for f in listing["files"]]
    folders = [f["name"] for f in listing["folders"]]
    print(f"       folders: {folders}")
    print(f"       files  : {files}")
    assert folders == ["Media"], "every folder must stay navigable"
    assert listing["hidden"] == 2, listing["hidden"]     # game.iso, readme.txt
    assert "game.iso" not in files and "readme.txt" not in files
check("only launchable files, all folders", t_listing_filters)


def t_exe_is_listed():
    """`.exe` is launchable too — dev builds and homebrew ship them."""
    listing = library.list_directory(FakeClient(), "HDD:\\games\\Call of Duty Black Ops")
    files = [f["file"] for f in listing["files"]]
    assert "installer.exe" in files, f".exe missing: {files}"
    assert library.is_launchable("a.exe") and library.is_launchable("A.EXE")
    assert library.is_launchable("a.xex") and library.is_launchable("a.xbe")
    assert not library.is_launchable("a.iso")
check(".exe files are listed", t_exe_is_listed)


def t_nothing_is_suppressed():
    """There is no 'primary executable wins' rule — the folder is the truth.

    A heuristic that picks one executable per folder hides files the user owns:
    every Call of Duty's multiplayer, and any `.exe` beside a `default.xex`.
    """
    listing = library.list_directory(FakeClient(), "HDD:\\games\\Call of Duty Black Ops")
    files = sorted(f["file"] for f in listing["files"])
    assert files == ["default.xex", "default_mp.xex", "installer.exe"], files
check("every launchable file survives", t_nothing_is_suppressed)


def t_listing_shapes():
    listing = library.list_directory(FakeClient(), "HDD:\\")
    assert [f["name"] for f in listing["folders"]] == ["Content", "games"], listing["folders"]
    assert listing["folders"][0]["path"] == "HDD:\\Content", listing["folders"][0]
    entry = listing["files"][0]
    assert entry["path"] == "HDD:\\xshell.xex", entry
    assert entry["dir"] == "HDD:" and entry["drive"] == "HDD", entry
    assert entry["size"] == 4096
    # Content is navigable — no folder is skipped for the user
    assert any(f["name"] == "Content" for f in listing["folders"])
check("entries carry path, dir, drive, size", t_listing_shapes)


def t_title_id_folder_in_listing():
    listing = library.list_directory(FakeClient(), "HDD:\\Content")
    folder = listing["folders"][0]
    assert folder["label"] == "Halo 3", folder
    assert folder["name"] == "4D5307E6", folder
check("title-ID folders show the game name", t_title_id_folder_in_listing)


def t_empty_folder():
    listing = library.list_directory(FakeClient(), "HDD:\\nothing")
    assert listing["folders"] == [] and listing["files"] == []
    assert listing["hidden"] == 2
check("unlaunchable folder reports what it hid", t_empty_folder)


def t_paths():
    assert library.join("HDD:\\", "games") == "HDD:\\games"
    assert library.join("HDD:\\games", "Halo 3") == "HDD:\\games\\Halo 3"
    assert library.parent_of("HDD:\\games\\Halo 3") == "HDD:\\games"
    assert library.parent_of("HDD:") is None
    assert library.parent_of("HDD:\\") is None
    # walking up to a drive must yield a listable root, not a bare "HDD:"
    assert library.parent_of("HDD:\\games") == "HDD:\\", library.parent_of("HDD:\\games")
check("path joining and walking up", t_paths)


def t_drive_roots_keep_their_separator():
    """The console answers 414 access denied to dirlist name="HDD:".

    Only ``HDD:\\`` can be listed — the bare form fails for every drive, which
    would make the whole browser unusable.
    """
    assert library.normalize_dir_path("HDD:") == "HDD:\\"
    assert library.normalize_dir_path("HDD:\\") == "HDD:\\"
    assert library.normalize_dir_path("HDD:\\games") == "HDD:\\games"

    drives = library.drive_entries(FakeClient())
    for drive in drives:
        assert drive["path"].endswith(":\\"), drive
        assert not drive["label"].endswith("\\"), "the separator is noise on a tile"
    assert [d["path"] for d in drives] == ["HDD:\\", "USB0:\\"], drives

    # and anything malformed reaching list_directory is repaired on the way out
    client = FakeClient()
    library.list_directory(client, "HDD:")
    assert client.reads == ["HDD:\\"], client.reads
check("drive roots stay listable", t_drive_roots_keep_their_separator)


def t_file_display():
    cod = library.file_entry("HDD:\\games\\Call of Duty", "default_mp.xex")
    solo = library.file_entry("HDD:\\games\\Halo 3", "default.xex")
    # alone in its folder: the title leads
    assert library.file_display(solo, siblings=False)[0] == "Halo 3"
    # sharing a folder: the executable leads, since the folder is in the header
    label, sub = library.file_display(cod, siblings=True)
    assert (label, sub) == ("Multiplayer", "default_mp.xex"), (label, sub)
    assert library.filename_is_informative(cod)
    assert not library.filename_is_informative(solo)
check("file rows lead with what distinguishes them", t_file_display)


# ── 5. store ──────────────────────────────────
print("\n[5] store")
def t_store():
    tmp = tempfile.mkdtemp()
    s = Store()
    s.data_dir = lambda: tmp
    s.host = "192.168.1.50"
    a = library.file_entry("HDD:\\games\\Halo 3", "default.xex")
    b = library.file_entry("HDD:\\games\\SR2", "default.xex")
    assert s.add_favorite(a) is True
    assert s.add_favorite(a) is False, "duplicate accepted"
    s.add_favorite(b)
    assert s.move_favorite(b["path"], -1) is True
    assert s.favorites[0]["name"] == "SR2"
    assert s.move_favorite(s.favorites[0]["path"], -1) is False
    s.save()

    again = Store()
    again.data_dir = lambda: tmp
    again.load()
    assert again.host == "192.168.1.50"
    assert [e["name"] for e in again.favorites] == ["SR2", "Halo 3"], again.favorites
    assert again.toggle_favorite(a) is False
    assert not again.is_favorite(a["path"])
check("favorites round-trip", t_store)


def t_save_failure_is_reported():
    """A favourite that cannot be written must say so, not vanish silently."""
    import os
    s = Store()
    unwritable = os.path.join(tempfile.mkdtemp(), "nope")
    s._resolved_dir = unwritable
    if os.name != "nt":
        os.makedirs(unwritable, exist_ok=True)
        os.chmod(unwritable, 0o500)
    else:
        # Windows honours a file where a directory is expected.
        with open(unwritable, "w") as fh:
            fh.write("not a directory")

    ok = s.add_favorite(library.file_entry("HDD:\\games\\Halo 3", "default.xex"))
    assert s.last_error, "a failed save must be recorded, not swallowed"
    assert "Not saving" in s.storage_status(), s.storage_status()
    print(f"       reported: {s.storage_status()[:70]}")

    # and it clears once a good directory is available
    s._resolved_dir = tempfile.mkdtemp()
    assert s.save() is True
    assert s.last_error == ""
check("a failed save is reported, not swallowed", t_save_failure_is_reported)


def t_directory_resolution():
    import os
    s = Store()
    good = tempfile.mkdtemp()

    # an explicitly adopted directory wins and is remembered
    s._resolved_dir = tempfile.mkdtemp()
    s.host = "192.168.1.50"
    s.add_favorite(library.file_entry("HDD:\\games\\Halo 3", "default.xex"))
    assert s.use_directory(good) is True
    assert s.data_dir() == good
    # settings written elsewhere are migrated, not abandoned
    assert os.path.isfile(os.path.join(good, Store.FILE_NAME)), os.listdir(good)
    assert s.host == "192.168.1.50"
    assert len(s.favorites) == 1, s.favorites

    # a directory that cannot be written is refused
    assert s.use_directory("") is False
    assert s.data_dir() == good, "a bad suggestion must not lose the good one"


check("storage directory resolution and migration", t_directory_resolution)


def t_candidates_never_empty():
    s = Store()
    candidates = s._candidate_dirs()
    assert candidates, "there must always be somewhere to try"
    assert any("xelauncher" in c.lower() or "storage" in c.lower() for c in candidates), candidates
    # whatever happens, data_dir returns a usable string
    assert isinstance(s.data_dir(), str) and s.data_dir()
check("a writable fallback always exists", t_candidates_never_empty)


def t_store_ignores_old_keys():
    """Unknown keys in a settings file are ignored, not fatal."""
    import json, os
    tmp = tempfile.mkdtemp()
    legacy = {
        "host": "192.168.1.50",
        "favorites": [{"name": "Halo 3", "path": "HDD:\\games\\Halo 3\\default.xex"}],
        # keys this build knows nothing about
        "library": [{"name": "x", "path": "y"}],
        "scan_depth": 3,
        "library_scan_version": 2,
    }
    with open(os.path.join(tmp, Store.FILE_NAME), "w", encoding="utf-8") as fh:
        json.dump(legacy, fh)
    s = Store()
    s.data_dir = lambda: tmp
    s.load()
    assert s.host == "192.168.1.50"
    assert len(s.favorites) == 1, s.favorites
check("old settings files still load", t_store_ignores_old_keys)


# ── 6. screens ────────────────────────────────
print("\n[6] screens")

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
        self.updates = 0
        self.peak_overlay = 0
    def update(self):
        self.updates += 1
        self.peak_overlay = max(self.peak_overlay, len(self.overlay))
    def run_task(self, fn, *a, **kw):
        self.tasks.append(fn)      # captured, not run: no I/O in a unit test


class FakeSession(Session):
    def __init__(self, connected=True):
        super().__init__()
        self._connected = connected
        self.console_name = "TESTBOX" if connected else ""
    @property
    def connected(self):
        return self._connected
    def current_title(self):
        return {"name": "Halo 3", "path": "HDD:\\games\\Halo 3\\default.xex"}
    def ensure(self):
        return (True, "TESTBOX")


COD_DIR = "HDD:\\games\\Call of Duty Black Ops"


def make_app(width=200, favorites=True, connected=True, cache=True):
    page = FakePage(width)
    app = App(page)
    app.store.data_dir = lambda: tempfile.mkdtemp()
    app.store.host = "192.168.1.50"
    if favorites:
        app.store.favorites = [
            library.file_entry("HDD:\\games\\Halo 3", "default.xex"),
            library.file_entry(COD_DIR, "default_mp.xex"),
        ]
    app.session = FakeSession(connected)
    if cache:
        # Seed the browse cache so screens render real content without I/O.
        client = FakeClient()
        app.browse_cache["\x00drives"] = {
            "path": None, "folders": library.drive_entries(client),
            "files": [], "hidden": 0,
        }
        for path in ("HDD:\\", "HDD:\\games", COD_DIR, "HDD:\\nothing"):
            app.browse_cache[path] = library.list_directory(client, path)
    app.apply_metrics()
    return app


def texts(control, out=None):
    """Every string rendered in a control tree — what the user would read."""
    out = [] if out is None else out
    for attr in ("value", "label"):
        value = getattr(control, attr, None)
        if isinstance(value, str) and value:
            out.append(value)
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                texts(c, out)
        elif child is not None and not isinstance(child, str):
            texts(child, out)
    return out


def find_control(control, predicate, out=None):
    """First control in the tree matching predicate."""
    if predicate(control):
        return control
    for attr in ("content", "controls", "trailing", "leading"):
        child = getattr(control, attr, None)
        children = child if isinstance(child, list) else ([child] if child is not None else [])
        for c in children:
            if isinstance(c, str):
                continue
            found = find_control(c, predicate)
            if found is not None:
                return found
    return None


for width, kind in ((200, "watch"), (400, "phone")):
    for name in SCREENS:
        for populated in (True, False):
            label = f"{kind}/{name}/{'populated' if populated else 'empty'}"
            def build(name=name, width=width, populated=populated):
                app = make_app(width, favorites=populated, cache=populated)
                assert app._build(name, {}) is not None
            check(label, build)


def t_console_offers_shutdown():
    rendered = texts(make_app()._build("console", {}))
    assert "Shutdown" in rendered, rendered
    assert any(text.startswith("Power off") for text in rendered), rendered
check("console offers shutdown", t_console_offers_shutdown)


# ── 7. the browser ────────────────────────────
print("\n[7] browsing on screen")

def t_browse_root_lists_drives():
    app = make_app()
    rendered = texts(app._build("browse", {}))
    print(f"       {[t for t in rendered if ':' in t or t == 'Console']}")
    assert "Console" in rendered, rendered
    assert "HDD:" in rendered and "USB0:" in rendered, rendered
check("top level lists the drives", t_browse_root_lists_drives)


def t_drive_tile_navigates_to_a_listable_path():
    """Tapping a drive must request "HDD:\\", the only form the console lists."""
    app = make_app()
    app.go("home")
    app.go("browse")
    drives = app.browse_cache["\x00drives"]["folders"]
    for drive in drives:
        app.go("browse", path=drive["path"])
        requested = app.stack[-1][1]["path"]
        assert requested.endswith(":\\"), f"would 414: {requested!r}"
        app.back()
check("tapping a drive asks for a valid path", t_drive_tile_navigates_to_a_listable_path)


def t_browse_drive_lists_folders():
    app = make_app()
    rendered = texts(app._build("browse", {"path": "HDD:\\"}))
    assert "games" in rendered, rendered
    assert "Content" in rendered, "Content must be browsable, not skipped"
    assert "xshell.xex" in rendered, "a loose executable at the drive root"
    assert "readme.txt" not in rendered
    assert any("1 other file" in t for t in rendered), rendered
check("a drive shows its real folders", t_browse_drive_lists_folders)


def t_browse_game_folder():
    app = make_app()
    rendered = texts(app._build("browse", {"path": COD_DIR}))
    print(f"       {[t for t in rendered if '.' in t or t in ('Campaign', 'Multiplayer')]}")
    for wanted in ("Campaign", "Multiplayer", "default.xex", "default_mp.xex",
                   "installer.exe", "Media"):
        assert wanted in rendered, f"{wanted!r} missing from {rendered}"
    assert "game.iso" not in rendered
check("a game folder shows all three executables", t_browse_game_folder)


def t_browse_navigates():
    app = make_app()
    app.go("home")
    app.go("browse")
    assert [s[0] for s in app.stack] == ["home", "browse"]
    # walking down pushes a view per level, so swipe-back walks up
    app.go("browse", path="HDD:\\")
    app.go("browse", path="HDD:\\games")
    assert [s[1].get("path") for s in app.stack] == [None, None, "HDD:\\", "HDD:\\games"]
    assert len(app.page.views) == 4
    app.back()
    assert app.stack[-1][1]["path"] == "HDD:\\"
    app.back(); app.back()
    assert [s[0] for s in app.stack] == ["home"]
check("each folder is a pushed view", t_browse_navigates)


def t_letter_filter():
    """Filtering has to work with no keyboard at all — some watches raise none."""
    listing = library.list_directory(FakeClient(), "HDD:\\")
    letters = library.listing_initials(listing)
    print(f"       initials: {letters}")
    assert letters == ["C", "G", "X"], letters      # Content, games, xshell.xex

    folders, files = library.filter_listing(listing, initial="G")
    assert [f["name"] for f in folders] == ["games"], folders
    assert files == []

    folders, files = library.filter_listing(listing, initial="X")
    assert folders == [] and [f["file"] for f in files] == ["xshell.xex"], (folders, files)

    # letter and text compose
    folders, files = library.filter_listing(listing, query="ame", initial="G")
    assert [f["name"] for f in folders] == ["games"], folders
    folders, files = library.filter_listing(listing, query="zzz", initial="G")
    assert folders == [] and files == []

    # digits and symbols group under "#", and sort last
    digits = {"folders": [{"name": "1UP", "label": "1UP"}],
              "files": [{"name": "Alpha", "file": "a.xex"}]}
    assert library.listing_initials(digits) == ["A", "#"], library.listing_initials(digits)
    folders, _ = library.filter_listing(digits, initial="#")
    assert [f["name"] for f in folders] == ["1UP"], folders

    assert library.initial_of("") == ""
    assert library.initial_of("halo") == "H"
    assert library.initial_of("4D5307E6") == "#"
check("letters filter without a keyboard", t_letter_filter)


def t_letter_picker_renders():
    app = make_app()
    view = app._build("browse", {"path": "HDD:\\"})
    # not shown until the user opens the filter
    assert "Tap to type" not in texts(view)

    from ui.screens import browse as browse_screen
    app2 = make_app()
    app2.params = {"path": "HDD:\\"}
    root = browse_screen.view(app2)
    toggle = find_control(
        root,
        lambda c: getattr(c, "on_click", None) is not None
        and find_control(c, lambda x: getattr(x, "icon", None) == ft.Icons.SEARCH) is not None,
    )
    toggle.on_click(None)
    rendered = texts(root)
    for letter in ("C", "G", "X"):
        assert letter in rendered, f"letter {letter} missing from {rendered}"

    # tapping a letter narrows the list without any typing
    cell = find_control(root, lambda c: getattr(c, "content", None) is not None
                        and getattr(getattr(c, "content", None), "value", None) == "G"
                        and getattr(c, "on_click", None) is not None)
    assert cell is not None, "no tappable G"
    cell.on_click(None)
    rendered = texts(root)
    assert "games" in rendered and "Content" not in rendered, rendered
    assert any("1 of 3" in t for t in rendered), rendered
check("tapping a letter filters the folder", t_letter_picker_renders)


def t_filter_listing():
    """A folder of 172 games needs narrowing, not scrolling."""
    listing = library.list_directory(FakeClient(), COD_DIR)
    listing["folders"].append({"name": "4D5307E6", "label": "Halo 3",
                               "path": "x", "is_directory": True})

    # 2 folders (Media + the title-ID one) and 3 files
    folders, files = library.filter_listing(listing, "")
    assert len(folders) + len(files) == 5, (folders, files)

    # matches the executable name
    folders, files = library.filter_listing(listing, "mp")
    assert [f["file"] for f in files] == ["default_mp.xex"], files
    assert folders == []

    # case-insensitive, and matches the title too
    _, files = library.filter_listing(listing, "INSTALLER")
    assert [f["file"] for f in files] == ["installer.exe"], files

    # a folder is findable by its raw name *or* its resolved game name
    folders, _ = library.filter_listing(listing, "4D53")
    assert [f["label"] for f in folders] == ["Halo 3"], folders
    folders, _ = library.filter_listing(listing, "halo")
    assert [f["label"] for f in folders] == ["Halo 3"], folders

    # no match is no match, not everything
    folders, files = library.filter_listing(listing, "zzzz")
    assert folders == [] and files == []
    # whitespace-only is treated as no filter
    folders, files = library.filter_listing(listing, "   ")
    assert len(folders) + len(files) == 5
check("filter matches names, files and title IDs", t_filter_listing)


def icons(control, out=None):
    """Every icon in a control tree. (ft.Icons members are enums, not strings.)"""
    out = [] if out is None else out
    for attr in ("icon", "action_icon"):
        value = getattr(control, attr, None)
        if value is not None and not isinstance(value, (list, dict)):
            out.append(value)
    for attr in ("content", "controls", "trailing", "leading"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                icons(c, out)
        elif child is not None and not isinstance(child, str):
            icons(child, out)
    return out


def t_search_is_reachable_on_screen():
    app = make_app()
    view = app._build("browse", {"path": "HDD:\\"})
    # Search owns the header's action slot and refresh sits in the list: the
    # frequent action is the one within thumb reach.
    assert ft.Icons.SEARCH in icons(view), "no way to start searching"
    assert "Refresh folder" in texts(view), texts(view)
check("search takes the header, refresh sits in the list", t_search_is_reachable_on_screen)


def t_browse_empty_folder():
    app = make_app()
    rendered = texts(app._build("browse", {"path": "HDD:\\nothing"}))
    assert "Nothing to launch" in rendered, rendered
    assert any("2 file" in t for t in rendered), rendered
check("a folder with nothing launchable says so", t_browse_empty_folder)


def t_browse_shows_spinner_before_load():
    app = make_app(cache=False)
    control = app._build("browse", {"path": "HDD:\\games"})
    assert control is not None
    assert app.page.tasks, "should have scheduled a load"
check("an uncached folder loads asynchronously", t_browse_shows_spinner_before_load)


def t_pin_from_browser():
    app = make_app(favorites=False)
    entry = library.file_entry(COD_DIR, "default_mp.xex")
    assert not app.store.is_favorite(entry["path"])
    actions.toggle_pin(app, entry)
    assert app.store.is_favorite(entry["path"]), "star should pin from the browser"
    rendered = texts(app._build("home", {}))
    assert any("Multiplayer" in t for t in rendered), rendered
check("pinning from the browser reaches home", t_pin_from_browser)


def t_home_points_at_browser():
    app = make_app(favorites=False)
    rendered = texts(app._build("home", {}))
    assert "Browse games" in rendered or "Games" in rendered, rendered
    assert not any("scan" in t.lower() for t in rendered), "home must not offer a scan"
check("home offers browsing, not scanning", t_home_points_at_browser)


def t_launch_dialog_names_executable():
    app = make_app()
    app.store.confirm_launch = True
    app.run_bg = lambda fn: None
    app.on_ui = lambda fn: fn()
    actions.launch_entry(app, library.file_entry(COD_DIR, "default_mp.xex"))
    rendered = texts(app.page.overlay[0])
    print(f"       dialog: {rendered}")
    assert "default_mp.xex" in rendered, rendered
    assert COD_DIR in rendered, rendered
check("launch dialog names the exact executable", t_launch_dialog_names_executable)


# ── 8. widgets ────────────────────────────────
print("\n[8] widgets")
def t_widgets():
    app = make_app()
    m = app.m
    w.tile(m, label="X", icon=ft.Icons.STAR, on_tap=lambda e: None, sub="s",
           sub_strong=True, trailing=w.star_toggle(m, True, lambda e: None))
    w.toggle_tile(m, label="T", value=True, on_toggle=lambda: None)
    w.header(m, "Title", on_back=lambda e: None, on_action=lambda e: None)
    w.status_chip(m, True, "TESTBOX", on_tap=lambda e: None)
    w.empty_state(m, icon=ft.Icons.STAR, heading="h", message="m")
    w.screen(m, [ft.Text("x")])
    w.screen(m, [ft.Text("x")], scrollable=False)
    dismiss = w.busy(app.page, m, "Working")
    assert len(app.page.overlay) == 1
    dismiss()
    assert len(app.page.overlay) == 0
    w.confirm(app.page, m, heading="Sure?", message="msg", detail="file.xex",
              confirm_label="Yes", on_confirm=lambda: None, tone="danger")
    assert "file.xex" in texts(app.page.overlay[0])
    app.page.overlay.clear()
    w.menu(app.page, m, "Halo 3", [("Launch", ft.Icons.PLAY_ARROW, lambda: None, "accent")],
           subheading="default.xex")
    assert "default.xex" in texts(app.page.overlay[0])
    app.page.overlay.clear()
    w.toast(app.page, m, "Hi")
    assert len(app.page.overlay) == 1
check("all widgets build", t_widgets)


# ── 9. metrics ────────────────────────────────
print("\n[9] metrics")
def t_metrics():
    watch = metrics_for(FakePage(192), round_screen=True)
    square = metrics_for(FakePage(192), round_screen=False)
    phone = metrics_for(FakePage(420), round_screen=True)
    assert watch.watch and not phone.watch
    assert watch.pad_h > square.pad_h
    assert watch.bg == "#000000"
    assert phone.max_content_width == 460
    assert metrics_for(FakePage(None)).watch
check("metrics", t_metrics)


# ── 10. navigation ────────────────────────────
print("\n[10] navigation")
def t_nav():
    app = make_app()
    app.go("home")
    assert len(app.page.views) == 1
    app.go("settings")
    assert [s[0] for s in app.stack] == ["home", "settings"]
    app.back()
    assert [s[0] for s in app.stack] == ["home"]
    app.back()
    assert [s[0] for s in app.stack] == ["home"], "back at root must be a no-op"
    app.go("connect")
    assert [s[0] for s in app.stack] == ["connect"] and len(app.page.views) == 1
    app.rebuild()
check("push/pop/reset", t_nav)


def t_routes_are_unique_and_views_are_not_replaced():
    """The two invariants that keep swipe-back working on a watch.

    Flet resolves a pop by matching View.route, so three folders deep — every
    one of them "/browse" — a shared route matches the wrong view and leaves
    one sitting invisibly on top, eating every tap. Replacing the destination
    View object on the way back has the same effect.
    """
    app = make_app()
    app.go("home")
    home_view = app.page.views[0]

    app.go("browse")
    app.go("browse", path="HDD:\\")
    app.go("browse", path="HDD:\\games")

    routes = [v.route for v in app.page.views]
    print(f"       routes: {routes}")
    assert len(set(routes)) == len(routes), f"duplicate routes: {routes}"
    assert len(app.page.views) == len(app.stack) == 4

    for _ in range(3):
        app.back()

    assert len(app.page.views) == 1 and len(app.stack) == 1
    assert app.page.views[0] is home_view, "home was replaced, not refreshed"
    assert "Games" in texts(home_view), "home lost its content on the way back"
check("routes stay unique, views are refreshed not replaced", t_routes_are_unique_and_views_are_not_replaced)


def t_back_tolerates_flet_having_already_popped():
    """A swipe pops on the Flutter side; back() must not pop one view too many."""
    app = make_app()
    app.go("home")
    app.go("browse")
    assert len(app.page.views) == 2

    # simulate Flet removing the view itself before the event reaches us
    app.page.views.pop()
    app.back()
    assert len(app.stack) == 1 and len(app.page.views) == 1, (len(app.stack), len(app.page.views))
    assert app.stack[0][0] == "home"
check("back() stays in sync however the pop arrived", t_back_tolerates_flet_having_already_popped)


def t_reentrant_go_does_not_strand():
    """A screen that navigates while being built must win over its own push."""
    app = make_app()
    app.go("home")

    original = SCREENS["console"]

    def leaves_immediately(a):
        a.go("home")
        return ft.Text("never shown")

    SCREENS["console"] = leaves_immediately
    try:
        app.go("console")
        assert [s[0] for s in app.stack] == ["home"], [s[0] for s in app.stack]
        assert len(app.page.views) == 1, len(app.page.views)
    finally:
        SCREENS["console"] = original
check("navigating during a build does not strand the user", t_reentrant_go_does_not_strand)


def open_search(app, path="HDD:\\"):
    """Build the browse screen and press its search toggle."""
    from ui.screens import browse as browse_screen
    app.params = {"path": path}
    root = browse_screen.view(app)
    toggle = find_control(
        root,
        lambda c: getattr(c, "on_click", None) is not None
        and find_control(c, lambda x: getattr(x, "icon", None) == ft.Icons.SEARCH) is not None,
    )
    assert toggle is not None, "no search toggle in the header"
    toggle.on_click(None)
    return root


def t_watch_typing_uses_our_own_keypad():
    """A watch may raise no IME at all, so typing must not need one.

    Same shape the platform's own apps use: search opens a dedicated input
    screen that owns its keys, rather than focusing an inline field.
    """
    app = make_app(200)
    root = open_search(app)

    assert find_control(root, lambda c: isinstance(c, ft.TextField)) is None,         "a watch should not rely on an inline field"
    chip = find_control(root, lambda c: getattr(c, "on_click", None) is not None
                        and "Tap to type" in texts(c))
    assert chip is not None, f"no way to start typing: {texts(root)}"

    chip.on_click(None)
    assert app.page.overlay, "keypad did not open"
    keypad = app.page.overlay[-1]
    rendered = texts(keypad)
    for char in ("A", "M", "Z", "0", "9"):
        assert char in rendered, f"key {char!r} missing from the keypad"

    # type "GAM" on our own keys, then press Done
    for char in "GAM":
        cell = find_control(keypad, lambda c, ch=char: getattr(c, "on_click", None) is not None
                            and getattr(getattr(c, "content", None), "value", None) == ch)
        assert cell is not None, f"no {char} key"
        cell.on_click(None)
    assert "GAM" in texts(app.page.overlay[-1]), texts(app.page.overlay[-1])

    done = find_control(keypad, lambda c: getattr(c, "on_click", None) is not None
                        and getattr(getattr(c, "content", None), "icon", None) == ft.Icons.CHECK)
    assert done is not None, "no Done key"
    done.on_click(None)

    assert "games" in texts(root), texts(root)
    assert "Content" not in texts(root), "filter did not apply after Done"
check("a watch types on our own keypad", t_watch_typing_uses_our_own_keypad)


def t_keypad_edits():
    app = make_app(200)
    captured = {}
    w.keypad(app.page, app.m, initial="AB", on_done=lambda v: captured.update(value=v))
    pad = app.page.overlay[-1]

    def tap_icon(icon):
        cell = find_control(pad, lambda c: getattr(c, "on_click", None) is not None
                            and getattr(getattr(c, "content", None), "icon", None) == icon)
        assert cell is not None, f"no {icon} key"
        cell.on_click(None)

    assert "AB" in texts(pad)
    tap_icon(ft.Icons.BACKSPACE_OUTLINED)
    assert "A" in texts(pad) and "AB" not in texts(pad)
    tap_icon(ft.Icons.CLOSE)                       # clear
    tap_icon(ft.Icons.CHECK)                       # done
    assert captured == {"value": ""}, captured
check("keypad backspace, clear and done", t_keypad_edits)


def t_phone_still_uses_a_real_field():
    """Where the system keyboard works, use it — and never rebuild it mid-edit."""
    app = make_app(400)
    root = open_search(app)

    field = find_control(root, lambda c: isinstance(c, ft.TextField))
    assert field is not None, "a phone should get a real text field"
    assert field.autofocus is not True, "code-focus stops the IME appearing"

    class Ev:
        def __init__(self, control):
            self.control = control

    field.value = "gam"
    field.on_change(Ev(field))
    again = find_control(root, lambda c: isinstance(c, ft.TextField))
    assert again is field, "the field was rebuilt — focus and keyboard would be lost"
    assert "games" in texts(root), texts(root)
    assert "Content" not in texts(root), "filter did not apply"
check("a phone keeps a real text field", t_phone_still_uses_a_real_field)


def t_fields_are_never_focused_from_code():
    """On Wear OS a code-focused field holds the cursor but raises no keyboard,
    and then will not raise one when tapped either. Only the user's tap works."""
    import inspect
    from ui.screens import browse as browse_screen, connect as connect_screen
    for module in (browse_screen, connect_screen):
        source = inspect.getsource(module)
        assert "autofocus=True" not in source, f"{module.__name__} autofocuses a field"
        assert ".focus()" not in source, f"{module.__name__} focuses from code"
check("no field is focused from code", t_fields_are_never_focused_from_code)


# ── 11. client ────────────────────────────────
print("\n[11] client")
def t_launch():
    sent = []
    class Conn:
        is_connected = True
        def send(self, data): sent.append(data.decode())
        def recv_line(self): return b"200- OK\r\n"
        def close(self): sent.append("<closed>")
        def connect(self): pass
    c = XbdmClient("192.168.1.50")
    c.conn = Conn()
    c.launch("HDD:\\games\\Halo 3\\default.xex")
    assert 'magicboot title="HDD:\\games\\Halo 3\\default.xex" directory="HDD:\\games\\Halo 3"' in sent[0], sent
    assert c.booting and "<closed>" in sent

    sent.clear()
    class DeadConn(Conn):
        def recv_line(self):
            from xbdm.exceptions import XbdmConnectionError
            raise XbdmConnectionError("Connection closed by console")
    c2 = XbdmClient("1.2.3.4"); c2.conn = DeadConn()
    c2.goto_dashboard()      # a dropped link mid-boot is success
    c3 = XbdmClient("1.2.3.4"); c3.conn = Conn()
    c3.reboot()
    assert "magicboot cold" in "".join(sent)
    sent.clear()
    c4 = XbdmClient("1.2.3.4"); c4.conn = Conn()
    c4.shutdown()
    assert 'consolefeatures ver=2 type=11 params="A\\0\\A\\0\\"' in "".join(sent)
    assert "<closed>" in sent
check("launch/dashboard/reboot/shutdown", t_launch)


def t_dirlist():
    class Conn:
        is_connected = True
        def __init__(self):
            self.lines = [
                b"202- multiline response follows\r\n",
                b'name="default.xex" sizehi=0x0 sizelo=0x4000 createhi=0x1 createlo=0x2\r\n',
                b'name="Media" sizehi=0x0 sizelo=0x0 createhi=0x1 createlo=0x2 directory\r\n',
                b".\r\n",
            ]
        def send(self, data): pass
        def recv_line(self): return self.lines.pop(0)
        def close(self): pass
    c = XbdmClient("1.2.3.4"); c.conn = Conn()
    entries = c.get_directory_contents("HDD:\\games\\Halo 3")
    assert entries[0] == {"name": "default.xex", "is_directory": False, "size": 0x4000}
    assert entries[1]["is_directory"] is True
check("dirlist parsing", t_dirlist)


def t_drivelist():
    class Conn:
        is_connected = True
        def __init__(self):
            self.lines = [b"202- ok\r\n", b'drivename="HDD"\r\n',
                          b'drivename="USB0"\r\n', b".\r\n"]
        def send(self, data): pass
        def recv_line(self): return self.lines.pop(0)
        def close(self): pass
    c = XbdmClient("1.2.3.4"); c.conn = Conn()
    assert c.get_drive_list() == ["HDD:\\", "USB0:\\"]
check("drivelist parsing", t_drivelist)


# ── 12. host validation ───────────────────────
print("\n[12] host validation")
def t_hosts():
    from xbdm.connection import normalize_host
    from xbdm.exceptions import XbdmConnectionError
    assert normalize_host(" 192.168.1.50 ") == "192.168.1.50"
    assert normalize_host("xbox360.local") == "xbox360.local"
    for bad in ("", "   ", "192.168.1.999", "not a host!"):
        try:
            normalize_host(bad)
            raise AssertionError(f"accepted {bad!r}")
        except XbdmConnectionError:
            pass
check("normalize_host", t_hosts)


print("\n" + "=" * 52)
if failures:
    print(f"{len(failures)} FAILURE(S)\n")
    for name, tb in failures:
        print(f"--- {name} ---\n{tb}")
    sys.exit(1)
print("ALL CHECKS PASSED")
