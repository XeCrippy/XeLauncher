from typing import Callable, Dict, Optional

import flet as ft

from core import library
from ui import widgets as w
from ui.theme import ACCENT


def launch_entry(app, entry: Dict, on_done: Optional[Callable] = None):
    if app.store.confirm_launch:
        w.confirm(
            app.page,
            app.m,
            heading=entry.get("name", "Launch?"),
            detail=entry.get("file") or None,
            message=entry.get("dir") or entry.get("path", ""),
            confirm_label="Launch",
            on_confirm=lambda: _do_launch(app, entry, on_done),
        )
        return
    _do_launch(app, entry, on_done)


def _do_launch(app, entry: Dict, on_done: Optional[Callable] = None):
    name = entry.get("name", "game")
    dismiss = w.busy(app.page, app.m, f"Launching\n{name}")

    def work():
        ok, message = app.session.launch(entry)

        def finish():
            dismiss()
            if ok:
                _launched_splash(app, entry)
            else:
                w.toast(app.page, app.m, message, tone="danger", seconds=3.0)
            if on_done:
                on_done()

        app.on_ui(finish)

    app.run_bg(work)


def _launched_splash(app, entry: Dict):
    m = app.m
    holder = []

    def close(_=None):
        if holder:
            w.close_overlay(app.page, holder[0])

    controls = [
        ft.Icon(ft.Icons.CHECK_CIRCLE, size=m.icon_large, color=ACCENT),
        w.title(m, "Launched"),
        w.caption(m, entry.get("name", "")),
    ]
    if library.filename_is_informative(entry):
        controls.append(w.detail_chip(m, entry["file"]))

    content = ft.Column(
        spacing=m.gap,
        tight=True,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=controls,
    )

    holder.append(
        ft.Container(
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.94, "#000000"),
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=m.pad_h, vertical=m.list_pad_v),
            on_click=close,
            content=content,
        )
    )
    app.page.overlay.append(holder[0])
    app.page.update()

    async def _expire():
        import asyncio

        await asyncio.sleep(1.8)
        close()

    app.page.run_task(_expire)


def toggle_pin(app, entry: Dict, on_done: Optional[Callable] = None):
    pinned = app.store.toggle_favorite(entry)

    if app.store.last_error:
        w.toast(
            app.page,
            app.m,
            "Could not save — check Settings › Storage",
            tone="danger",
            seconds=4.0,
        )
    else:
        w.toast(
            app.page,
            app.m,
            "Pinned to home" if pinned else "Unpinned",
            tone="accent-soft" if pinned else "surface",
            seconds=1.4,
        )

    if on_done:
        on_done()


def console_action(app, runner: Callable, busy_text: str, on_done: Optional[Callable] = None):
    dismiss = w.busy(app.page, app.m, busy_text)

    def work():
        ok, message = runner()

        def finish():
            dismiss()
            w.toast(
                app.page,
                app.m,
                message,
                tone="accent-soft" if ok else "danger",
                seconds=2.0 if ok else 3.0,
            )
            if on_done:
                on_done()

        app.on_ui(finish)

    app.run_bg(work)
