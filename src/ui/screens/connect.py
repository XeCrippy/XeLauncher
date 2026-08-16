import threading
import time

import flet as ft

from ui import widgets as w
from ui.theme import ACCENT, DANGER, TEXT_DIM, TEXT_FAINT
from xbdm import discovery


def view(app):
    m = app.m
    page = app.page

    state = {
        "mode": "start",       # start | connecting | scanning | results | manual | error
        "found": [],
        "done": 0,
        "total": 254,
        "message": "",
        "error": "",
        "manual_full": False,
        "octet": "",
        "full": app.store.host or "",
    }
    stop_event = threading.Event()
    prefix = discovery.subnet_prefix()
    last_paint = {"at": 0.0}

    auto = app.params.get("auto", True)

    root = ft.Container(expand=True)

    def paint():
        root.content = build()
        page.update()

    def set_mode(mode: str, **extra):
        state["mode"] = mode
        state.update(extra)
        paint()

    # ── flows ─────────────────────────────────
    def begin():
        """Decide what to do the moment the screen appears."""
        if auto and app.store.host and app.store.auto_connect:
            connect_to(app.store.host, saved=True)
        else:
            start_scan()

    def connect_to(host: str, saved: bool = False):
        set_mode("connecting", message=host, error="")

        def work():
            ok, message = app.session.connect(host)

            def finish():
                if ok:
                    app.store.set_host(host)
                    app.go("home")
                    return
                if saved:
                    start_scan(note=f"{host} did not answer")
                else:
                    set_mode("error", error=message, message=host)

            app.on_ui(finish)

        app.run_bg(work)

    def start_scan(note: str = ""):
        stop_event.clear()
        set_mode("scanning", found=[], done=0, total=254, error="", message=note)

        def on_found(ip: str):
            state["found"].append(ip)
            app.on_ui(paint)

        def on_progress(done: int, total: int):
            state["done"] = done
            state["total"] = total
            now = time.monotonic()
            if now - last_paint["at"] < 0.1 and done < total:
                return
            last_paint["at"] = now
            app.on_ui(paint)

        def work():
            try:
                found = discovery.find_consoles(
                    on_found=on_found, on_progress=on_progress, stop=stop_event
                )
                error = "" if found else "No consoles answered"
            except discovery.XbdmDiscoveryError as ex:
                found, error = [], str(ex)

            def finish():
                if stop_event.is_set():
                    return
                if len(found) == 1:
                    connect_to(found[0])
                    return
                set_mode("results" if found else "error", found=found, error=error)

            app.on_ui(finish)

        app.run_bg(work)

    def cancel_scan(_=None):
        stop_event.set()
        set_mode("results" if state["found"] else "manual")

    def on_octet(e):
        state["octet"] = e.control.value

    def on_full(e):
        state["full"] = e.control.value

    octet_input = ft.TextField(
        value="",
        dense=True,
        text_align=ft.TextAlign.CENTER,
        text_size=m.size_title,
        keyboard_type=ft.KeyboardType.NUMBER,
        max_length=3,
        hint_text="120",
        on_change=on_octet,
    )

    full_input = ft.TextField(
        value=app.store.host or "",
        dense=True,
        text_align=ft.TextAlign.CENTER,
        text_size=m.size_label,
        keyboard_type=ft.KeyboardType.URL,
        hint_text="192.168.1.120",
        on_change=on_full,
    )

    def submit_manual(_=None):
        if state["manual_full"] or not prefix:
            host = (state["full"] or "").strip()
        else:
            octet = (state["octet"] or "").strip()
            host = f"{prefix}.{octet}" if octet else ""

        if not host:
            w.toast(page, m, "Enter an address", tone="danger", seconds=1.6)
            return
        connect_to(host)

    # ── screen bodies ─────────────────────────
    def build():
        mode = state["mode"]
        if mode in ("start", "connecting"):
            return connecting_body()
        if mode == "scanning":
            return scanning_body()
        if mode == "results":
            return results_body()
        if mode == "manual":
            return manual_body()
        return error_body()

    def connecting_body():
        return w.screen(
            m,
            [
                ft.ProgressRing(width=m.icon_large, height=m.icon_large,
                                stroke_width=3, color=ACCENT),
                w.title(m, "Connecting"),
                w.caption(m, state["message"] or "…"),
            ],
            scrollable=False,
        )

    def scanning_body():
        done, total = state["done"], max(1, state["total"])
        controls = [
            ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.Stack(
                    width=m.icon_large + 22,
                    height=m.icon_large + 22,
                    controls=[
                        ft.Container(
                            alignment=ft.Alignment.CENTER,
                            content=ft.ProgressRing(
                                width=m.icon_large + 22,
                                height=m.icon_large + 22,
                                stroke_width=3,
                                value=done / total,
                                color=ACCENT,
                            ),
                        ),
                        ft.Container(
                            alignment=ft.Alignment.CENTER,
                            content=ft.Text(
                                f"{int(done / total * 100)}%",
                                size=m.size_sub,
                                color=TEXT_DIM,
                            ),
                        ),
                    ],
                ),
            ),
            w.title(m, "Searching"),
            w.caption(m, state["message"] or "Looking for consoles on Wi-Fi"),
        ]

        for ip in state["found"]:
            controls.append(
                w.tile(m, label=ip, icon=ft.Icons.VIDEOGAME_ASSET, tone="accent",
                       on_tap=lambda e, host=ip: connect_to(host))
            )

        controls.append(w.tile(m, label="Cancel", icon=ft.Icons.CLOSE,
                               on_tap=cancel_scan, tone="ghost"))
        return w.screen(m, controls)

    def results_body():
        controls = [w.header(m, "Consoles")]
        for ip in state["found"]:
            controls.append(
                w.tile(m, label=ip, icon=ft.Icons.VIDEOGAME_ASSET, sub="Tap to connect",
                       tone="surface", on_tap=lambda e, host=ip: connect_to(host))
            )
        controls.append(w.tile(m, label="Search again", icon=ft.Icons.REFRESH,
                               on_tap=lambda e: start_scan(), tone="ghost"))
        controls.append(w.tile(m, label="Enter IP", icon=ft.Icons.KEYBOARD,
                               on_tap=lambda e: set_mode("manual"), tone="ghost"))
        return w.screen(m, controls)

    def manual_body():
        controls = [w.header(m, "Console IP")]

        if prefix and not state["manual_full"]:
            controls.append(
                ft.Container(
                    padding=ft.Padding.only(top=2, bottom=2),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Row(
                        spacing=4,
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(f"{prefix}.", size=m.size_title, color=TEXT_FAINT),
                            ft.Container(width=64, content=octet_input),
                        ],
                    ),
                )
            )
            controls.append(w.caption(m, "Only the last part is needed"))
        else:
            controls.append(full_input)

        controls.append(w.tile(m, label="Connect", icon=ft.Icons.LINK,
                               on_tap=submit_manual, tone="accent"))

        if prefix:
            controls.append(
                w.tile(
                    m,
                    label="Full address" if not state["manual_full"] else "Last part only",
                    icon=ft.Icons.EDIT,
                    tone="ghost",
                    on_tap=lambda e: set_mode("manual", manual_full=not state["manual_full"]),
                )
            )
        controls.append(w.tile(m, label="Search Wi-Fi", icon=ft.Icons.WIFI_FIND,
                               on_tap=lambda e: start_scan(), tone="ghost"))
        return w.screen(m, controls)

    def error_body():
        controls = [
            ft.Container(height=m.gap),
            ft.Icon(ft.Icons.WIFI_OFF, size=m.icon_large, color=DANGER),
            w.title(m, "No console"),
            w.caption(m, state["error"] or "Nothing answered on this network"),
            ft.Container(height=2),
            w.tile(m, label="Search again", icon=ft.Icons.REFRESH,
                   on_tap=lambda e: start_scan(), tone="accent"),
            w.tile(m, label="Enter IP", icon=ft.Icons.KEYBOARD,
                   on_tap=lambda e: set_mode("manual"), tone="surface"),
        ]
        if app.store.host:
            controls.append(
                w.tile(m, label=f"Retry {app.store.host}", icon=ft.Icons.HISTORY,
                       tone="ghost", on_tap=lambda e: connect_to(app.store.host))
            )
        controls.append(
            ft.Container(
                padding=ft.Padding.only(top=m.gap),
                alignment=ft.Alignment.CENTER,
                content=ft.Text(
                    "Console needs xbdm running\nand the same Wi-Fi",
                    size=m.size_small,
                    color=TEXT_FAINT,
                    text_align=ft.TextAlign.CENTER,
                ),
            )
        )
        return w.screen(m, controls)

    root.content = connecting_body()

    async def _start():
        begin()

    page.run_task(_start)
    return root
