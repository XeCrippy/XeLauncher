import os
import threading
import time
from collections import deque
from typing import Optional

import flet as ft

from core.boxart import ArtCache
from core.session import Session
from core.store import Store
from ui import widgets as w
from ui.screens import browse as browse_screen
from ui.screens import connect as connect_screen
from ui.screens import console as console_screen
from ui.screens import home as home_screen
from ui.screens import settings as settings_screen
from ui.theme import app_theme, metrics_for

SCREENS = {
    "connect": connect_screen.view,
    "home": home_screen.view,
    "browse": browse_screen.view,
    "console": console_screen.view,
    "settings": settings_screen.view,
}

#: Screens that reset the navigation stack — you never go "back" into the
#: connect flow from the home screen, or back into home from connect.
ROOT_SCREENS = {"home", "connect"}


class App:
    """Shared context every screen is handed: page, store, session, navigation.

    Navigation is a stack of Flet views, which is what makes Wear OS
    swipe-to-dismiss and the Android back button behave natively. Two
    invariants keep ``page.views`` and :attr:`stack` in agreement, and breaking
    either leaves an invisible route on top that swallows every tap:

    1. **Every pushed view gets a unique route.** Flet resolves a pop by
       matching ``View.route``, so three folders deep — all of them
       ``/browse`` — it would match the wrong view. Routes carry a sequence
       number: ``/browse/1``, ``/browse/2``, …
    2. **A pushed view is never swapped out.** Refreshing replaces its
       *controls*, so the route keeps its identity and Flutter is only ever
       asked to push or pop.
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self.store = Store()
        self.session = Session()
        self.m = metrics_for(page, self.store.round_screen)
        #: (screen name, params, view) mirroring ``page.views`` one-for-one.
        self.stack: list[tuple[str, dict, ft.View]] = []
        #: Makes every pushed route unique — see invariant 1 above.
        self._route_seq: int = 0
        #: Bumped on every committed navigation, so a screen that navigates
        #: while being built can be detected and deferred to.
        self._nav_seq: int = 0
        #: Params of the screen currently being built.
        self.params: dict = {}
        #: Directory listings already fetched this session, keyed by console
        #: path. Walking back up the tree should not re-ask the console for a
        #: folder it just described; the refresh button drops an entry when the
        #: user wants it re-read.
        self.browse_cache: dict = {}

        # ── box art ───────────────────────────
        #: Covers and title IDs, cached on disk beside the settings.
        self.art = ArtCache(os.path.join(self.store.data_dir(), "art"))
        #: Entries waiting for a cover, and the paths already queued, so a
        #: repaint cannot enqueue the same game a second time.
        self._art_queue: deque = deque()
        self._art_queued: set = set()
        self._art_worker: Optional[threading.Thread] = None
        self._art_lock = threading.Lock()

    # ── layout ────────────────────────────────
    def apply_metrics(self):
        self.m = metrics_for(self.page, self.store.round_screen)

    # ── navigation ────────────────────────────
    def go(self, name: str, **params):
        if name in ROOT_SCREENS:
            self.stack = []
            self.page.views.clear()

        token = self._nav_seq
        view = self._build(name, params)
        if self._nav_seq != token:
            return

        self.stack.append((name, params, view))
        self.page.views.append(view)
        self._nav_seq += 1
        self.page.update()

    def back(self, e=None):
        if len(self.stack) <= 1:
            return

        self.stack.pop()
        if len(self.page.views) > len(self.stack):
            self.page.views.pop()

        self._refresh_top()
        self._nav_seq += 1
        self.page.update()

    def rebuild(self):
        if not self.stack:
            return
        self._refresh_top()
        self.page.update()

    def _refresh_top(self):
        """Re-render the top view's contents without replacing the view."""
        name, params, view = self.stack[-1]
        self.params = params or {}
        view.bgcolor = self.m.bg
        view.controls = [ft.SafeArea(expand=True, content=SCREENS[name](self))]

    def _build(self, name: str, params: dict) -> ft.View:
        self.params = params or {}
        content = SCREENS[name](self)
        self._route_seq += 1
        return ft.View(
            route=f"/{name}/{self._route_seq}",
            padding=0,
            spacing=0,
            bgcolor=self.m.bg,
            controls=[ft.SafeArea(expand=True, content=content)],
        )

    # ── box art ───────────────────────────────
    def reload_art_cache(self):
        """Point the cache at wherever settings actually ended up living."""
        self.art = ArtCache(os.path.join(self.store.data_dir(), "art"))

    def art_for(self, entry: dict) -> Optional[bytes]:
        """This entry's cover as raw PNG bytes if it is ready, else None.

        Never blocks: a cover that is not cached yet is requested in the
        background and appears on a later repaint.
        """
        if not self.store.box_art:
            return None
        blob = self.art.art_bytes(entry)
        if blob is None:
            self.request_art(entry)
        return blob

    def request_art(self, entry: dict):
        """Queue a cover lookup for one game."""
        path = (entry.get("path") or "").lower()
        if not path or not self.store.box_art:
            return
        if self.art.cached_art(entry) or self.art.is_hopeless(entry):
            return

        with self._art_lock:
            if path in self._art_queued:
                return
            self._art_queued.add(path)
            self._art_queue.append(dict(entry))
            already_running = self._art_worker is not None and self._art_worker.is_alive()
            if already_running:
                return
            self._art_worker = threading.Thread(target=self._drain_art, daemon=True)
            self._art_worker.start()

    def _drain_art(self):
        """Resolve queued covers one at a time, repainting as they land.

        Strictly serial. Every title ID costs a console round trip on the one
        socket the app owns, and racing those against the directory listing
        the user is actually waiting for would make browsing feel slower to
        buy pictures nobody asked for yet.
        """
        painted = 0.0

        while True:
            with self._art_lock:
                if not self._art_queue:
                    self._art_worker = None
                    break
                entry = self._art_queue.popleft()

            found = False
            try:
                found = bool(
                    self.art.resolve(entry, read_range=self.session.read_range)
                )
            except Exception:
                found = False

            # Coalesce repaints: covers arrive one by one, and redrawing the
            # screen for each of thirty games would cost more than it shows.
            now = time.monotonic()
            with self._art_lock:
                idle = not self._art_queue
            if found and (idle or now - painted > 0.8):
                painted = now
                self.on_ui(self.rebuild)

            time.sleep(0.01)   # leave the socket free for the user's taps

    # ── threading ─────────────────────────────
    def run_bg(self, fn):
        """Run *fn* on a worker thread, surfacing any crash as a toast.

        Console I/O must never block Flet's loop, and a worker that dies
        silently leaves the user staring at a spinner that will never stop.
        """

        def runner():
            try:
                fn()
            except Exception as ex:
                message = str(ex) or type(ex).__name__
                try:
                    self.on_ui(lambda: w.toast(self.page, self.m, message[:90],
                                               tone="danger", seconds=3.0))
                except Exception:
                    pass

        threading.Thread(target=runner, daemon=True).start()

    def on_ui(self, fn):
        """Marshal *fn* back onto Flet's loop and repaint.

        The counterpart to :meth:`run_bg` — worker threads must never touch
        controls directly.
        """

        async def runner():
            fn()
            self.page.update()

        self.page.run_task(runner)


def main(page: ft.Page):
    page.title = "XeLauncher"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = app_theme()
    page.padding = 0
    page.spacing = 0

    _size_preview_window(page)

    app = App(page)
    page.bgcolor = app.m.bg

    def on_view_pop(e=None):
        app.back()

    def on_resize(e=None):
        was_watch = app.m.watch
        app.apply_metrics()
        if app.m.watch != was_watch:
            page.bgcolor = app.m.bg
            app.rebuild()

    async def resolve_storage():
        if page.platform not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            return
        try:
            directory = await ft.StoragePaths().get_application_support_directory()
        except Exception:
            return
        if directory and app.store.use_directory(str(directory)):
            # Settings may have just been read from a different location, and
            # the art cache lives beside them.
            app.reload_art_cache()
            app.rebuild()

    page.on_view_pop = on_view_pop
    page.on_resize = on_resize
    page.run_task(resolve_storage)

    app.go("connect")


def _size_preview_window(page: ft.Page):
    """On desktop, open at watch size so the real layout is what you see.

    ``XELAUNCHER_PREVIEW=phone`` opens a phone-shaped window instead. Ignored
    entirely on Android, where the window is the display.
    """
    if page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        return

    if os.getenv("XELAUNCHER_PREVIEW", "watch").lower() == "phone":
        page.window.width, page.window.height = 380, 660
    else:
        page.window.width, page.window.height = 240, 240
    page.window.resizable = True
