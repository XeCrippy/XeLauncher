from typing import Dict, List

import flet as ft

from core import library
from core.titles import basename
from ui import actions
from ui import widgets as w
from ui.theme import ACCENT, TEXT_DIM, TEXT_FAINT
from xbdm import XbdmError


def view(app):
    m = app.m
    page = app.page
    store = app.store

    path = app.params.get("path")
    cache_key = path or "\x00drives"

    state = {
        "loading": True,
        "listing": app.browse_cache.get(cache_key),
        "error": "",
        #: Filter text. Applies to this folder only — it narrows what is on
        #: screen rather than searching the console, which would mean walking
        #: the whole drive over the network for every keystroke.
        "query": "",
        #: Single starting letter, chosen from the picker. Needs no keyboard.
        "initial": "",
        "searching": False,
    }
    if state["listing"] is not None:
        state["loading"] = False

    root = ft.Container(expand=True)

    def paint():
        root.content = build()
        page.update()

    # ── loading ───────────────────────────────
    def load(force: bool = False):
        if not force and state["listing"] is not None:
            return

        state["loading"] = True
        state["error"] = ""

        def work():
            listing = None
            error = ""
            try:
                ok, message = app.session.ensure()
                if not ok:
                    error = message
                elif path is None:
                    listing = {
                        "path": None,
                        "folders": library.drive_entries(app.session.client),
                        "files": [],
                        "hidden": 0,
                    }
                else:
                    listing = library.list_directory(app.session.client, path)
            except XbdmError as ex:
                error = ex.friendly
            except Exception as ex:
                error = str(ex) or "Could not read that folder"

            def finish():
                state["loading"] = False
                state["listing"] = listing
                state["error"] = error
                if listing is not None:
                    app.browse_cache[cache_key] = listing
                paint()

            app.on_ui(finish)

        app.run_bg(work)

    def refresh(_=None):
        app.browse_cache.pop(cache_key, None)
        state["listing"] = None
        load(force=True)
        paint()

    # ── filtering ─────────────────────────────
    def on_query(e):
        state["query"] = e.control.value or ""
        paint()

    search_input = ft.TextField(
        value="",
        dense=True,
        hint_text="Tap to type",
        prefix_icon=ft.Icons.SEARCH,
        text_size=m.size_label,
        on_change=on_query,
    )

    def toggle_search(_=None):
        state["searching"] = not state["searching"]
        if not state["searching"]:
            state["query"] = ""
            state["initial"] = ""
            search_input.value = ""
        paint()

    def pick_initial(letter: str):
        state["initial"] = letter
        paint()

    def open_keypad(_=None):
        """Hand typing to a screen that owns its own keys.

        The same shape Wear OS apps use for search: never focus an inline
        field, because a watch may raise no keyboard for it at all.
        """
        def done(value: str):
            state["query"] = value
            search_input.value = value
            paint()

        w.keypad(page, m, initial=state["query"], on_done=done,
                 heading=heading())

    def query_chip() -> ft.Control:
        typed = state["query"]
        return w.tile(
            m,
            label=typed or "Tap to type",
            icon=ft.Icons.KEYBOARD,
            tone="raised" if typed else "ghost",
            on_tap=open_keypad,
            trailing=(
                w.icon_action(m, ft.Icons.BACKSPACE_OUTLINED,
                              lambda e: (state.update(query=""), paint()))
                if typed else None
            ),
        )

    def search_panel(listing: Dict) -> List[ft.Control]:
        # A watch gets our own keypad; anything with a real keyboard gets a
        # real text field, where the system IME behaves.
        controls: List[ft.Control] = [
            query_chip() if m.watch
            else ft.Container(padding=ft.Padding.only(bottom=2), content=search_input)
        ]
        letters = library.listing_initials(listing)
        if len(letters) > 1:
            controls.append(
                w.letter_picker(m, letters, state["initial"], pick_initial)
            )
        return controls

    # ── per-file interactions ─────────────────
    def pin(entry: Dict):
        actions.toggle_pin(app, entry, paint)

    def file_menu(entry: Dict):
        pinned = store.is_favorite(entry["path"])
        w.menu(
            page,
            m,
            entry.get("name", "Game"),
            [
                ("Launch", ft.Icons.PLAY_ARROW,
                 lambda: actions.launch_entry(app, entry), "accent"),
                (
                    "Unpin" if pinned else "Pin to home",
                    ft.Icons.STAR_BORDER if pinned else ft.Icons.STAR,
                    lambda: pin(entry),
                    "surface",
                ),
            ],
            subheading=entry.get("file") or None,
        )

    # ── rows ──────────────────────────────────
    def folder_tile(folder: Dict) -> ft.Control:
        # A folder named as a title ID displays as the game; keep the raw name
        # underneath so the console's own structure is still legible.
        sub = folder["name"] if folder["label"] != folder["name"] else None
        return w.tile(
            m,
            label=folder["label"],
            sub=sub,
            icon=ft.Icons.FOLDER,
            tone="surface",
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, size=m.icon, color=TEXT_FAINT),
            on_tap=lambda e, target=folder["path"]: app.go("browse", path=target),
        )

    def file_tile(entry: Dict, siblings: bool) -> ft.Control:
        label, sub = library.file_display(entry, siblings=siblings)
        pinned = store.is_favorite(entry["path"])
        return w.tile(
            m,
            label=label,
            sub=sub,
            sub_strong=siblings or library.filename_is_informative(entry),
            icon=ft.Icons.TERMINAL if siblings else ft.Icons.SPORTS_ESPORTS,
            art=app.art_for(entry),
            tone="surface",
            on_tap=lambda e, ent=entry: actions.launch_entry(app, ent),
            on_long_press=lambda e, ent=entry: file_menu(ent),
            trailing=w.star_toggle(m, pinned, lambda e, ent=entry: pin(ent)),
        )

    # ── body ──────────────────────────────────
    def heading() -> str:
        if path is None:
            return "Console"
        return library.folder_label(basename(path)) or path

    def breadcrumb() -> ft.Control:
        return ft.Container(
            padding=ft.Padding.only(bottom=2),
            alignment=ft.Alignment.CENTER,
            content=ft.Text(
                path,
                size=m.size_small,
                color=TEXT_FAINT,
                text_align=ft.TextAlign.CENTER,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )

    def build() -> ft.Control:
        controls: List[ft.Control] = [
            w.header(
                m, heading(), on_back=app.back, on_action=toggle_search,
                action_icon=ft.Icons.CLOSE if state["searching"] else ft.Icons.SEARCH,
            )
        ]
        if not state["searching"] and path:
            controls.append(breadcrumb())

        if state["loading"]:
            controls.append(
                ft.Container(
                    height=m.tile_height * 2,
                    alignment=ft.Alignment.CENTER,
                    content=ft.ProgressRing(width=m.icon_large, height=m.icon_large,
                                            stroke_width=3, color=ACCENT),
                )
            )
            return w.screen(m, controls)

        if state["error"]:
            controls.extend(
                w.empty_state(
                    m,
                    icon=ft.Icons.SYNC_PROBLEM,
                    heading="Could not open",
                    message=state["error"],
                    action_label="Try again",
                    on_action=refresh,
                )
            )
            return w.screen(m, controls)

        listing = state["listing"] or {"folders": [], "files": [], "hidden": 0}
        total = len(listing["folders"]) + len(listing["files"])

        if state["searching"]:
            controls[1:1] = search_panel(listing)

        folders, files = library.filter_listing(
            listing, state["query"], state["initial"]
        )
        filtering = bool(state["query"].strip() or state["initial"])

        if filtering:
            shown = len(folders) + len(files)
            controls.append(
                ft.Container(
                    padding=ft.Padding.only(bottom=2),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        f"{shown} of {total}" if shown else "No match",
                        size=m.size_small,
                        color=TEXT_DIM if shown else TEXT_FAINT,
                    ),
                )
            )
            if not shown:
                return w.screen(m, controls)

        if not folders and not files:
            controls.extend(
                w.empty_state(
                    m,
                    icon=ft.Icons.FOLDER_OFF,
                    heading="Nothing to launch",
                    message=(
                        f"{listing['hidden']} file(s) here, none launchable."
                        if listing["hidden"]
                        else "This folder is empty."
                    ),
                )
            )
            return w.screen(m, controls)

        controls.extend(folder_tile(folder) for folder in folders)

        if files:
            if folders:
                controls.append(w.section(m, "Launchable"))
            siblings = len(files) > 1
            controls.extend(file_tile(entry, siblings) for entry in files)

        if listing["hidden"] and not filtering:
            controls.append(
                ft.Container(
                    padding=ft.Padding.only(top=m.gap),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        f"{listing['hidden']} other file(s) hidden",
                        size=m.size_small,
                        color=TEXT_DIM,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
            )

        controls.append(
            w.tile(m, label="Refresh folder", icon=ft.Icons.REFRESH,
                   tone="ghost", on_tap=refresh)
        )
        return w.screen(m, controls)

    root.content = build()

    if state["listing"] is None:
        async def _load():
            load()

        page.run_task(_load)

    return root
