"""Path checks: console paths under posixpath (Android), and the listing filter."""
import sys
import traceback

import pathlib
SRC = str(pathlib.Path(__file__).resolve().parents[1] / "src")
sys.path.insert(0, SRC)

# ── isolation ─────────────────────────────────
# Redirect every Store to a throwaway directory and stub the subnet sweep
# BEFORE anything imports them, so the suite can never sweep the LAN or
# overwrite the user's saved console and favourites.
import tempfile
import core.store as _store_module
_store_module.SRC_DIR = pathlib.Path(tempfile.mkdtemp())

from xbdm import discovery as _discovery
_discovery.find_consoles = lambda **kw: []
_discovery.local_ip = lambda: "192.168.1.5"

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as ex:
        failures.append((name, traceback.format_exc()))
        print(f"  FAIL {name}: {ex}")


from core import library
from core.titles import basename, label_for


# ── 1. posix path handling ────────────────────
print("\n[1] console paths under posixpath (i.e. on the watch)")

def t_basename_posix():
    """Console paths are backslash-separated whatever the host OS is.

    On Android posixpath finds no "/" and would hand back the whole string, so
    every game would be labelled with its full path.
    """
    import os, posixpath
    real = os.path
    os.path = posixpath
    try:
        assert basename("HDD:\\games\\Halo 3") == "Halo 3"
        assert basename("HDD:\\games\\Halo 3\\") == "Halo 3"
        assert basename("HDD:") == "HDD:"
        assert label_for("HDD:\\games\\Halo 3", "default.xex") == "Halo 3"
        assert label_for("HDD:\\Content\\0000\\4D5307E6", "default.xex") == "Halo 3"
        assert library.join("HDD:\\", "games") == "HDD:\\games"
        assert library.parent_of("HDD:\\games\\Halo 3") == "HDD:\\games"
        entry = library.file_entry("HDD:\\games\\Halo 3", "default.xex")
        assert entry["name"] == "Halo 3", entry
        assert entry["path"] == "HDD:\\games\\Halo 3\\default.xex", entry
    finally:
        os.path = real
check("labels and paths are correct with posixpath", t_basename_posix)


# ── 2. the only filter is the extension ───────
print("\n[2] listing filter")

class Client:
    def __init__(self, entries):
        self.entries = entries
    def get_drive_list(self):
        return ["HDD:\\"]
    def get_directory_contents(self, path):
        return self.entries


def t_extensions():
    entries = [
        {"name": "a.xex", "is_directory": False},
        {"name": "b.XEX", "is_directory": False},
        {"name": "c.xbe", "is_directory": False},
        {"name": "d.exe", "is_directory": False},
        {"name": "e.EXE", "is_directory": False},
        {"name": "f.iso", "is_directory": False},
        {"name": "g.bin", "is_directory": False},
        {"name": "h", "is_directory": False},
    ]
    listing = library.list_directory(Client(entries), "HDD:\\x")
    files = sorted(f["file"].lower() for f in listing["files"])
    print(f"       kept: {files}")
    assert files == ["a.xex", "b.xex", "c.xbe", "d.exe", "e.exe"], files
    assert listing["hidden"] == 3, listing["hidden"]
check("all three extensions, any case", t_extensions)


def t_nothing_is_skipped():
    """No folder is hidden from the user — Content and Cache included."""
    entries = [
        {"name": "Content", "is_directory": True},
        {"name": "Cache", "is_directory": True},
        {"name": "$SystemUpdate", "is_directory": True},
        {"name": "games", "is_directory": True},
    ]
    listing = library.list_directory(Client(entries), "HDD:\\")
    names = sorted(f["name"] for f in listing["folders"])
    assert names == ["$SystemUpdate", "Cache", "Content", "games"], names
    for folder in listing["folders"]:
        assert folder["path"].startswith("HDD:\\"), folder
check("every folder stays navigable", t_nothing_is_skipped)


def t_sorting():
    entries = [
        {"name": "zebra", "is_directory": True},
        {"name": "Alpha", "is_directory": True},
        {"name": "z.xex", "is_directory": False},
        {"name": "A.xex", "is_directory": False},
    ]
    listing = library.list_directory(Client(entries), "HDD:\\x")
    assert [f["name"] for f in listing["folders"]] == ["Alpha", "zebra"]
    assert [f["file"] for f in listing["files"]] == ["A.xex", "z.xex"]
check("folders and files sort case-insensitively", t_sorting)


def t_weird_names():
    entries = [
        {"name": "", "is_directory": False},
        {"name": "ok.xex", "is_directory": False},
        {"is_directory": True},
    ]
    listing = library.list_directory(Client(entries), "HDD:\\x")
    assert [f["file"] for f in listing["files"]] == ["ok.xex"], listing["files"]
    assert listing["folders"] == []
check("blank entries are ignored, not crashed on", t_weird_names)


# ── 3. where settings get written ─────────────
print("\n[3] storage resolution")

import os
from core.store import Store


def with_android(env, fn):
    """Run fn() as though we were inside a packaged Android app."""
    import core.store as store_module
    real_is_android = store_module._is_android
    saved = {k: os.environ.get(k) for k in ("FLET_APP_STORAGE_DATA", "FLET_APP_STORAGE_TEMP")}
    store_module._is_android = lambda: True
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        return fn()
    finally:
        store_module._is_android = real_is_android
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def t_android_uses_flet_dir():
    good = tempfile.mkdtemp()
    def go():
        s = Store()
        assert s.data_dir() == good, s.data_dir()
        s.favorites = [{"name": "Halo 3", "path": "HDD:\\g\\default.xex"}]
        assert s.save() is True, s.last_error
        again = Store()
        assert len(again.favorites) == 1, again.favorites
        return True
    assert with_android({"FLET_APP_STORAGE_DATA": good,
                         "FLET_APP_STORAGE_TEMP": None}, go)
check("normal Android: uses Flet's app data dir", t_android_uses_flet_dir)


def t_android_falls_back_when_unwritable():
    """An unwritable app data dir must fall back, not lose data.

    Falling through to /data/local/tmp — outside the app sandbox — and
    swallowing the PermissionError makes favourites silently evaporate.
    """
    blocked = os.path.join(tempfile.mkdtemp(), "blocked")
    with open(blocked, "w") as fh:            # a file where a dir should be
        fh.write("x")
    fallback = tempfile.mkdtemp()

    def go():
        s = Store()
        resolved = s.data_dir()
        print(f"       unwritable primary -> resolved to {resolved!r}")
        assert resolved == fallback, resolved
        s.favorites = [{"name": "Halo 3", "path": "HDD:\\g\\default.xex"}]
        assert s.save() is True, s.last_error
        assert s.last_error == ""
        return True

    assert with_android({"FLET_APP_STORAGE_DATA": blocked,
                         "FLET_APP_STORAGE_TEMP": fallback}, go)
check("unwritable app dir falls back instead of losing data", t_android_falls_back_when_unwritable)


def t_never_writes_outside_the_sandbox():
    """/data/local/tmp must never be chosen — it is not the app's to write to."""
    good = tempfile.mkdtemp()
    def go():
        s = Store()
        assert "/data/local/tmp" not in s.data_dir(), s.data_dir()
        assert all("/data/local/tmp" not in c for c in s._candidate_dirs())
        return True
    assert with_android({"FLET_APP_STORAGE_DATA": good, "FLET_APP_STORAGE_TEMP": None}, go)
check("never writes outside the app sandbox", t_never_writes_outside_the_sandbox)


print("\n" + "=" * 52)
if failures:
    for name, tb in failures:
        print(f"--- {name} ---\n{tb}")
    sys.exit(1)
print("ALL CHECKS PASSED")
