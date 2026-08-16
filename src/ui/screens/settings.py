import flet as ft

from core.version import APP_VERSION
from ui import widgets as w
from ui.theme import TEXT_FAINT


def view(app):
    m = app.m
    page = app.page
    store = app.store

    def refresh():
        app.rebuild()

    # ── handlers ──────────────────────────────
    def change_console(_=None):
        app.session.disconnect()
        app.go("connect", auto=False)

    def toggle_auto_connect():
        store.auto_connect = not store.auto_connect
        store.save()
        refresh()

    def toggle_confirm_launch():
        store.confirm_launch = not store.confirm_launch
        store.save()
        refresh()

    def toggle_round():
        store.round_screen = not store.round_screen
        store.save()
        app.apply_metrics()
        app.rebuild()

    def toggle_box_art():
        store.box_art = not store.box_art
        store.save()
        refresh()

    def art_cache_sub() -> str:
        """How much has been downloaded, so the setting is not abstract."""
        import os

        directory = app.art.directory
        try:
            covers = [n for n in os.listdir(directory) if n.endswith(".png")]
        except OSError:
            covers = []
        if not covers:
            return "Nothing cached yet"
        size = 0
        for name in covers:
            try:
                size += os.path.getsize(os.path.join(directory, name))
            except OSError:
                pass
        return f"{len(covers)} cover(s), {size // 1024} KB"

    def clear_art(_=None):
        app.art.clear()
        w.toast(page, m, "Art cache cleared", seconds=1.4)
        refresh()

    def clear_favorites(_=None):
        w.confirm(
            page,
            m,
            heading="Unpin everything?",
            message=f"{len(store.favorites)} game(s) will be removed from home.",
            confirm_label="Unpin all",
            tone="danger",
            on_confirm=lambda: (store.clear_favorites(), refresh()),
        )

    # ── body ──────────────────────────────────
    controls = [
        w.header(m, "Settings", on_back=app.back),

        w.section(m, "Console"),
        w.tile(
            m,
            label=store.host or "Not set",
            sub="Tap to change console",
            icon=ft.Icons.ROUTER,
            tone="surface",
            on_tap=change_console,
        ),
        w.toggle_tile(
            m,
            label="Auto connect",
            sub="Connect on open",
            icon=ft.Icons.BOLT,
            value=store.auto_connect,
            on_toggle=toggle_auto_connect,
        ),

        w.section(m, "Games"),
        w.toggle_tile(
            m,
            label="Confirm launch",
            sub="Ask before booting",
            icon=ft.Icons.TOUCH_APP,
            value=store.confirm_launch,
            on_toggle=toggle_confirm_launch,
        ),
        w.tile(
            m,
            label="Unpin all",
            sub=f"{len(store.favorites)} pinned",
            icon=ft.Icons.STAR_BORDER,
            tone="ghost",
            on_tap=clear_favorites,
            disabled=not store.favorites,
        ),

        w.section(m, "Display"),
        w.toggle_tile(
            m,
            label="Box art",
            sub="Downloads covers from Xbox Live",
            icon=ft.Icons.IMAGE,
            value=store.box_art,
            on_toggle=toggle_box_art,
        ),
        w.tile(
            m,
            label="Clear art cache",
            sub=art_cache_sub(),
            icon=ft.Icons.HIDE_IMAGE,
            tone="ghost",
            on_tap=clear_art,
        ),
        w.toggle_tile(
            m,
            label="Round screen",
            sub="Wider side margins",
            icon=ft.Icons.CIRCLE_OUTLINED,
            value=store.round_screen,
            on_toggle=toggle_round,
        ),

        w.section(m, "Storage"),
        w.tile(
            m,
            label="Saving to" if not store.last_error else "Not saving",
            sub=store.storage_status(),
            icon=ft.Icons.SAVE if not store.last_error else ft.Icons.SAVE_AS,
            tone="surface" if not store.last_error else "danger",
            sub_strong=bool(store.last_error),
            on_tap=lambda e: w.toast(page, m, store.storage_status(), seconds=6.0),
        ),

        ft.Container(
            padding=ft.Padding.only(top=m.gap * 2),
            alignment=ft.Alignment.CENTER,
            content=ft.Text(
                f"XeLauncher {APP_VERSION}\nSolace 360",
                size=m.size_small,
                color=TEXT_FAINT,
                text_align=ft.TextAlign.CENTER,
            ),
        ),
    ]

    return w.screen(m, controls)
