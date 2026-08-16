"""Flow checks: startup, the connect state machine and the launch path, no network."""
import asyncio
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
# overwrite the user's saved console and cached library.
import tempfile
import core.store as _store_module
_store_module.SRC_DIR = pathlib.Path(tempfile.mkdtemp())

from xbdm import discovery as _discovery
_discovery.find_consoles = lambda **kw: []
_discovery.local_ip = lambda: "192.168.1.5"

import flet as ft
from ui import shell, widgets as w
from ui.screens import connect as connect_screen
from xbdm import discovery

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as ex:
        failures.append((name, traceback.format_exc()))
        print(f"  FAIL {name}: {type(ex).__name__}: {ex}")


class FakeWindow:
    width = height = 0
    resizable = False


class FakePage:
    """Runs scheduled coroutines immediately, so async flows actually execute."""

    def __init__(self, width=200, platform=ft.PagePlatform.ANDROID):
        self.width = self.height = width
        self.overlay, self.views = [], []
        self.platform = platform
        self.window = FakeWindow()
        self.theme = self.theme_mode = self.bgcolor = None
        self.padding = self.spacing = 0
        self.title = ""
        self.on_view_pop = self.on_resize = None
        self.updates = 0
        self.peak_overlay = 0

    def update(self):
        self.updates += 1
        self.peak_overlay = max(self.peak_overlay, len(self.overlay))

    def run_task(self, fn, *a, **kw):
        result = fn(*a, **kw)
        if asyncio.iscoroutine(result):
            try:
                asyncio.run(result)
            except RuntimeError:
                # A coroutine scheduled from inside another asyncio.run (a
                # toast's own dismiss timer, say). Flet's real loop handles
                # this; here there is nothing left to drive it with.
                result.close()


# ── 1. shell.main on both platforms ───────────
print("\n[1] shell.main()")

def t_main_android():
    page = FakePage(platform=ft.PagePlatform.ANDROID)
    shell.main(page)
    assert page.theme is not None and page.theme_mode == ft.ThemeMode.DARK
    assert page.title == "XeLauncher"
    assert page.on_view_pop and page.on_resize
    assert len(page.views) == 1, page.views
    assert page.window.width == 0, "must not resize a window on Android"
check("android startup", t_main_android)


def t_main_desktop():
    page = FakePage(platform=ft.PagePlatform.WINDOWS)
    shell.main(page)
    assert page.window.width == 240 and page.window.height == 240, (page.window.width, page.window.height)
check("desktop startup sizes to a watch", t_main_desktop)


def t_main_desktop_phone_preview():
    import os
    os.environ["XELAUNCHER_PREVIEW"] = "phone"
    try:
        page = FakePage(platform=ft.PagePlatform.WINDOWS)
        shell.main(page)
        assert (page.window.width, page.window.height) == (380, 660), page.window.width
    finally:
        os.environ.pop("XELAUNCHER_PREVIEW")
check("XELAUNCHER_PREVIEW=phone", t_main_desktop_phone_preview)


def t_resize_switch():
    page = FakePage(200, platform=ft.PagePlatform.ANDROID)
    shell.main(page)
    page.width = 500          # phone rotated / window dragged wide
    page.on_resize(None)
    assert page.bgcolor is not None
check("resize handler", t_resize_switch)


# ── 2. connect flows, no network ──────────────
print("\n[2] connect flows")

def make_app(page=None, host="", auto=True):
    page = page or FakePage(200)
    app = shell.App(page)
    tmp = tempfile.mkdtemp()
    app.store.data_dir = lambda: tmp
    app.store.host = host
    app.store.auto_connect = auto
    return app


class StubSession:
    def __init__(self, ok=True):
        self.ok = ok
        self.connected = False
        self.console_name = ""
        self.calls = []

    def connect(self, host):
        self.calls.append(host)
        if self.ok:
            self.connected = True
            self.console_name = "TESTBOX"
            return True, "TESTBOX"
        return False, "Console did not answer"

    def disconnect(self):
        self.connected = False

    def ensure(self):
        return (self.connected, self.console_name or "No console")

    def current_title(self):
        return None


def t_auto_connect_to_home():
    app = make_app(host="192.168.1.50", auto=True)
    app.session = StubSession(ok=True)
    app.run_bg = lambda fn: fn()          # synchronous worker
    app.on_ui = lambda fn: fn()
    app.go("connect")
    assert app.session.calls == ["192.168.1.50"], app.session.calls
    assert [s[0] for s in app.stack] == ["home"], [x[0] for x in app.stack]
    assert app.store.host == "192.168.1.50"
check("saved console -> straight to home", t_auto_connect_to_home)


def t_saved_console_stale_falls_back_to_scan():
    swept = {"n": 0}

    def fake_find(on_found=None, on_progress=None, stop=None, first_only=False):
        swept["n"] += 1
        if on_progress:
            on_progress(254, 254)
        return []

    original = discovery.find_consoles
    connect_screen.discovery.find_consoles = fake_find
    try:
        app = make_app(host="192.168.1.99", auto=True)
        app.session = StubSession(ok=False)
        app.run_bg = lambda fn: fn()
        app.on_ui = lambda fn: fn()
        app.go("connect")
        assert swept["n"] == 1, "stale host should trigger a sweep"
        assert [s[0] for s in app.stack] == ["connect"], [x[0] for x in app.stack]
    finally:
        connect_screen.discovery.find_consoles = original
check("stale saved host -> auto sweep", t_saved_console_stale_falls_back_to_scan)


def t_single_result_auto_connects():
    def fake_find(on_found=None, on_progress=None, stop=None, first_only=False):
        if on_found:
            on_found("192.168.1.77")
        return ["192.168.1.77"]

    original = discovery.find_consoles
    connect_screen.discovery.find_consoles = fake_find
    try:
        app = make_app(host="", auto=True)
        app.session = StubSession(ok=True)
        app.run_bg = lambda fn: fn()
        app.on_ui = lambda fn: fn()
        app.go("connect")
        assert app.session.calls == ["192.168.1.77"], app.session.calls
        assert [s[0] for s in app.stack] == ["home"], [x[0] for x in app.stack]
        assert app.store.host == "192.168.1.77"
    finally:
        connect_screen.discovery.find_consoles = original
check("one console found -> connects without asking", t_single_result_auto_connects)


def t_multiple_results_offers_choice():
    def fake_find(on_found=None, on_progress=None, stop=None, first_only=False):
        for ip in ("192.168.1.10", "192.168.1.11"):
            if on_found:
                on_found(ip)
        return ["192.168.1.10", "192.168.1.11"]

    original = discovery.find_consoles
    connect_screen.discovery.find_consoles = fake_find
    try:
        app = make_app()
        app.session = StubSession(ok=True)
        app.run_bg = lambda fn: fn()
        app.on_ui = lambda fn: fn()
        app.go("connect")
        assert [s[0] for s in app.stack] == ["connect"], "should wait for the user"
        assert app.session.calls == [], app.session.calls
    finally:
        connect_screen.discovery.find_consoles = original
check("two consoles -> user picks", t_multiple_results_offers_choice)


def t_settings_change_console_skips_autoconnect():
    app = make_app(host="192.168.1.50", auto=True)
    app.session = StubSession(ok=True)
    app.run_bg = lambda fn: fn()
    app.on_ui = lambda fn: fn()

    called = {"find": 0}

    def fake_find(**kw):
        called["find"] += 1
        return []

    original = discovery.find_consoles
    connect_screen.discovery.find_consoles = fake_find
    try:
        app.go("connect", auto=False)
        assert app.session.calls == [], "auto=False must not reconnect silently"
        assert called["find"] == 1, "should sweep instead"
    finally:
        connect_screen.discovery.find_consoles = original
check("auto=False -> sweeps, never silently reconnects", t_settings_change_console_skips_autoconnect)


# ── 3. launch flow ────────────────────────────
print("\n[3] launch flow")

def t_launch_flow():
    from ui import actions
    app = make_app(host="192.168.1.50")
    launched = {}

    class S(StubSession):
        def launch(self, entry):
            launched["entry"] = entry
            return True, entry["name"]

    app.session = S()
    app.run_bg = lambda fn: fn()
    app.on_ui = lambda fn: fn()
    entry = {"name": "Halo 3", "path": "HDD:\\Games\\Halo 3\\default.xex", "dir": "HDD:\\Games\\Halo 3"}
    actions.launch_entry(app, entry)
    assert launched["entry"]["path"].endswith("default.xex"), launched
    assert app.page.peak_overlay >= 1, "should show the launched splash"
check("tap -> launch", t_launch_flow)


def t_launch_confirm_gate():
    from ui import actions
    app = make_app(host="192.168.1.50")
    app.store.confirm_launch = True
    calls = {"n": 0}

    class S(StubSession):
        def launch(self, entry):
            calls["n"] += 1
            return True, "ok"

    app.session = S()
    app.run_bg = lambda fn: fn()
    app.on_ui = lambda fn: fn()
    actions.launch_entry(app, {"name": "Halo 3", "path": "p", "dir": "d"})
    assert calls["n"] == 0, "confirm_launch must gate the boot"
    assert app.page.peak_overlay >= 1, "confirm overlay should be up"
check("confirm_launch gates the boot", t_launch_confirm_gate)


def t_launch_failure_reports():
    from ui import actions
    app = make_app(host="192.168.1.50")

    class S(StubSession):
        def launch(self, entry):
            return False, "That file is no longer on the console"

    app.session = S()
    app.run_bg = lambda fn: fn()
    app.on_ui = lambda fn: fn()
    actions.launch_entry(app, {"name": "Gone", "path": "p", "dir": "d"})
    assert app.page.peak_overlay >= 1, "failure should be visible, not silent"
check("launch failure surfaces", t_launch_failure_reports)


# ── 4. worker guard ───────────────────────────
print("\n[4] error handling")

def t_run_bg_guard():
    page = FakePage(200)
    app = shell.App(page)
    tmp = tempfile.mkdtemp()
    app.store.data_dir = lambda: tmp
    import threading
    done = threading.Event()

    def boom():
        done.set()
        raise RuntimeError("kaboom")

    app.run_bg(boom)
    done.wait(2)
    import time
    time.sleep(0.3)
    assert page.peak_overlay >= 1, "a crashing worker must show something"
check("worker exceptions surface as a toast", t_run_bg_guard)


print("\n" + "=" * 52)
if failures:
    print(f"{len(failures)} FAILURE(S)\n")
    for name, tb in failures:
        print(f"--- {name} ---\n{tb}")
    sys.exit(1)
print("ALL CHECKS PASSED")
