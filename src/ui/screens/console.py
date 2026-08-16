import flet as ft

from ui import actions
from ui import widgets as w
from ui.theme import TEXT_FAINT


def view(app):
    m = app.m
    page = app.page
    session = app.session

    state = {"title": None, "loading": True}
    root = ft.Container(expand=True)

    def paint():
        root.content = build()
        page.update()

    # ── now playing ───────────────────────────
    def load_current_title():
        def work():
            running = session.current_title() if session.connected else None

            def finish():
                state["title"] = running
                state["loading"] = False
                paint()

            app.on_ui(finish)

        app.run_bg(work)

    # ── actions ───────────────────────────────
    def dashboard(_=None):
        w.confirm(
            page,
            m,
            heading="Go to dashboard?",
            message="Closes whatever is running.",
            confirm_label="Dashboard",
            on_confirm=lambda: actions.console_action(
                app, session.goto_dashboard, "Returning to dashboard", load_current_title
            ),
        )

    def reboot(_=None):
        w.confirm(
            page,
            m,
            heading="Reboot console?",
            message="Any unsaved game progress is lost.",
            confirm_label="Reboot",
            tone="danger",
            on_confirm=lambda: actions.console_action(
                app, session.reboot, "Rebooting console", load_current_title
            ),
        )

    def shutdown(_=None):
        w.confirm(
            page,
            m,
            heading="Shut down console?",
            message="Any unsaved game progress is lost.",
            confirm_label="Shutdown",
            tone="danger",
            on_confirm=lambda: actions.console_action(
                app, session.shutdown, "Shutting down console", load_current_title
            ),
        )

    def reconnect(_=None):
        dismiss = w.busy(page, m, "Reconnecting")

        def work():
            ok, message = session.ensure()

            def finish():
                dismiss()
                w.toast(page, m, message if not ok else f"Connected to {message}",
                        tone="danger" if not ok else "accent-soft", seconds=2.0)
                load_current_title()

            app.on_ui(finish)

        app.run_bg(work)

    def disconnect(_=None):
        session.disconnect()
        app.go("connect")

    # ── body ──────────────────────────────────
    def now_playing():
        if state["loading"]:
            return ft.Container(
                height=m.tile_height,
                alignment=ft.Alignment.CENTER,
                content=ft.ProgressRing(width=m.icon, height=m.icon,
                                        stroke_width=2, color=TEXT_FAINT),
            )

        running = state["title"]
        if not running:
            return ft.Container(
                padding=ft.Padding.symmetric(vertical=4),
                alignment=ft.Alignment.CENTER,
                content=ft.Text("On the dashboard", size=m.size_sub, color=TEXT_FAINT),
            )

        return w.tile(
            m,
            label=running["name"],
            sub="Running now",
            icon=ft.Icons.PLAY_CIRCLE,
            tone="accent-soft",
            on_tap=lambda e: w.toast(page, m, running["path"], seconds=3.0),
        )

    def build():
        connected = session.connected
        controls = [
            w.header(m, "Console", on_back=app.back),
            w.status_chip(
                m,
                connected,
                session.console_name or app.store.host or "Not connected",
            ),
            now_playing(),
            w.section(m, "Actions"),
            w.tile(m, label="Dashboard", icon=ft.Icons.HOME, tone="surface",
                   sub="Close the running game", on_tap=dashboard, disabled=not connected),
            w.tile(m, label="Reboot", icon=ft.Icons.RESTART_ALT, tone="surface",
                   sub="Cold restart", on_tap=reboot, disabled=not connected),
            w.tile(m, label="Shutdown", icon=ft.Icons.POWER_SETTINGS_NEW, tone="surface",
                   sub="Power off (requires SRPC or JRPC2)", on_tap=shutdown,
                   disabled=not connected),
            w.section(m, "Connection"),
            w.tile(m, label="Reconnect", icon=ft.Icons.SYNC, tone="ghost", on_tap=reconnect),
            w.tile(m, label="Switch console", icon=ft.Icons.SWAP_HORIZ, tone="ghost",
                   on_tap=disconnect),
        ]
        return w.screen(m, controls)

    root.content = build()
    load_current_title()
    return root
