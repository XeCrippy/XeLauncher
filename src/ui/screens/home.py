from typing import Dict

import flet as ft

from core import library
from ui import actions
from ui import widgets as w


def view(app):
    m = app.m
    store = app.store

    def refresh():
        app.rebuild()

    # ── per-game interactions ─────────────────
    def launch(entry: Dict):
        actions.launch_entry(app, entry)

    def game_sub(entry: Dict) -> str:
        """The line under a pinned game: drive, plus the file when it matters."""
        drive = entry.get("drive", "")
        if library.filename_is_informative(entry):
            return f"{drive} · {entry['file']}" if drive else entry["file"]
        return drive

    def game_menu(entry: Dict):
        index = _index_of(store.favorites, entry["path"])
        items = [
            ("Launch", ft.Icons.PLAY_ARROW, lambda: launch(entry), "accent"),
        ]
        if index > 0:
            items.append(("Move up", ft.Icons.ARROW_UPWARD,
                          lambda: (store.move_favorite(entry["path"], -1), refresh()), "surface"))
        if 0 <= index < len(store.favorites) - 1:
            items.append(("Move down", ft.Icons.ARROW_DOWNWARD,
                          lambda: (store.move_favorite(entry["path"], 1), refresh()), "surface"))
        items.append(("Unpin", ft.Icons.STAR_BORDER,
                      lambda: actions.toggle_pin(app, entry, refresh), "surface"))

        w.menu(app.page, m, entry.get("name", "Game"), items,
               subheading=entry.get("file") or None)

    def game_tile(entry: Dict) -> ft.Control:
        return w.tile(
            m,
            label=entry.get("name", "?"),
            sub=game_sub(entry),
            sub_strong=library.filename_is_informative(entry),
            icon=ft.Icons.SPORTS_ESPORTS,
            art=app.art_for(entry),
            tone="surface",
            on_tap=lambda e, ent=entry: launch(ent),
            on_long_press=lambda e, ent=entry: game_menu(ent),
        )

    # ── assembly ──────────────────────────────
    connected = app.session.connected
    controls = [
        w.status_chip(
            m,
            connected,
            app.session.console_name or store.host or "Not connected",
            on_tap=lambda e: app.go("console" if connected else "connect"),
        )
    ]

    if store.favorites:
        controls.extend(game_tile(entry) for entry in store.favorites)
    else:
        controls.extend(
            w.empty_state(
                m,
                icon=ft.Icons.STAR_BORDER,
                heading="No games pinned",
                message="Browse the console, then star the games you want here.",
                action_label="Browse games",
                on_action=lambda e: app.go("browse"),
            )
        )

    controls.append(w.section(m, "Console"))
    controls.append(
        w.tile(m, label="Games", icon=ft.Icons.FOLDER_OPEN, tone="surface",
               sub="Browse drives and folders", on_tap=lambda e: app.go("browse"))
    )
    controls.append(
        w.tile(m, label="Power", icon=ft.Icons.POWER_SETTINGS_NEW, tone="surface",
               on_tap=lambda e: app.go("console"))
    )
    controls.append(
        w.tile(m, label="Settings", icon=ft.Icons.SETTINGS, tone="ghost",
               on_tap=lambda e: app.go("settings"))
    )

    return w.screen(m, controls)


def _index_of(entries, path: str) -> int:
    key = path.lower()
    for index, entry in enumerate(entries):
        if entry["path"].lower() == key:
            return index
    return -1
