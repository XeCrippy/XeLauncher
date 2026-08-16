import asyncio
from typing import Callable, List, Optional

import flet as ft

from ui.theme import (
    ACCENT,
    ACCENT_SOFT,
    DANGER,
    Metrics,
    ON_ACCENT,
    SURFACE,
    SURFACE_HIGH,
    TEXT,
    TEXT_DIM,
    TEXT_FAINT,
    WARNING,
)

#: tone name → (background, foreground, icon colour)
TONES = {
    "surface": (SURFACE, TEXT, TEXT_DIM),
    "raised": (SURFACE_HIGH, TEXT, TEXT_DIM),
    "accent": (ACCENT, ON_ACCENT, ON_ACCENT),
    "accent-soft": (ACCENT_SOFT, TEXT, ACCENT),
    "danger": (DANGER, "#1A0509", "#1A0509"),
    "ghost": (None, TEXT_DIM, TEXT_FAINT),
}


# ── text ──────────────────────────────────────
def title(m: Metrics, text: str, color: str = TEXT) -> ft.Text:
    return ft.Text(
        text,
        size=m.size_title,
        weight=ft.FontWeight.W_600,
        color=color,
        text_align=ft.TextAlign.CENTER,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )


def caption(m: Metrics, text: str, color: str = TEXT_DIM, align=ft.TextAlign.CENTER) -> ft.Text:
    return ft.Text(text, size=m.size_sub, color=color, text_align=align, max_lines=3)


def section(m: Metrics, text: str) -> ft.Container:
    """A quiet divider label — "Games", "Console" — between groups of tiles."""
    return ft.Container(
        padding=ft.Padding.only(left=m.tile_pad_h, top=m.gap, bottom=2),
        content=ft.Text(
            text.upper(),
            size=m.size_small,
            color=TEXT_FAINT,
            weight=ft.FontWeight.W_600,
        ),
    )


# ── tiles ─────────────────────────────────────
def tile(
    m: Metrics,
    *,
    label: str,
    icon: Optional[str] = None,
    sub: Optional[str] = None,
    on_tap: Optional[Callable] = None,
    on_long_press: Optional[Callable] = None,
    trailing: Optional[ft.Control] = None,
    tone: str = "surface",
    disabled: bool = False,
    sub_strong: bool = False,
    art: Optional[bytes] = None,
) -> ft.Container:
    bg, fg, icon_color = TONES.get(tone, TONES["surface"])
    muted = tone in ("surface", "raised", "ghost")

    text_column = [
        ft.Text(
            label,
            size=m.size_label,
            weight=ft.FontWeight.W_500,
            color=fg,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
    ]
    if sub:
        text_column.append(
            ft.Text(
                sub,
                # A sub-label carrying real information (an executable name, a
                # storage warning) gets a size and a weight up: the faintest
                # grey at the smallest size is unreadable at arm's length.
                size=m.size_sub if sub_strong else m.size_small,
                weight=ft.FontWeight.W_500 if sub_strong else ft.FontWeight.NORMAL,
                color=(TEXT if sub_strong else TEXT_DIM) if muted else fg,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )

    row: List[ft.Control] = []
    if art:
        # A cover replaces the icon rather than joining it: at 200px wide there
        # is room for one thing on the left, and the cover says more.
        size = m.tile_height - 16
        row.append(
            ft.Image(
                src=art,
                width=size,
                height=size,
                fit=ft.BoxFit.COVER,
                border_radius=6,
                # If the bytes are ever unreadable, fall back to the icon
                # instead of leaving a hole in the row.
                error_content=ft.Icon(icon or ft.Icons.SPORTS_ESPORTS,
                                      size=m.icon, color=icon_color),
            )
        )
    elif icon:
        row.append(ft.Icon(icon, size=m.icon, color=icon_color))
    row.append(
        ft.Column(
            spacing=0,
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=text_column,
        )
    )
    if trailing is not None:
        row.append(trailing)

    return ft.Container(
        height=m.tile_height,
        bgcolor=bg,
        border_radius=m.tile_radius,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.10, TEXT)) if tone == "ghost" else None,
        padding=ft.Padding.symmetric(horizontal=m.tile_pad_h),
        alignment=ft.Alignment.CENTER_LEFT,
        ink=not disabled and on_tap is not None,
        on_click=None if disabled else on_tap,
        on_long_press=None if disabled else on_long_press,
        opacity=0.45 if disabled else 1.0,
        content=ft.Row(
            spacing=m.gap + 4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=row,
        ),
    )


def toggle_tile(
    m: Metrics,
    *,
    label: str,
    value: bool,
    on_toggle: Callable,
    sub: Optional[str] = None,
    icon: Optional[str] = None,
) -> ft.Container:
    return tile(
        m,
        label=label,
        sub=sub,
        icon=icon,
        on_tap=lambda e=None: on_toggle(),
        trailing=ft.Icon(
            ft.Icons.TOGGLE_ON if value else ft.Icons.TOGGLE_OFF,
            size=m.icon + 8,
            color=ACCENT if value else TEXT_FAINT,
        ),
    )


def icon_action(m: Metrics, icon: str, on_click: Callable, color: str = TEXT_DIM,
                tooltip: Optional[str] = None) -> ft.Container:
    return ft.Container(
        width=44,
        height=44,
        border_radius=22,
        alignment=ft.Alignment.CENTER,
        ink=True,
        on_click=on_click,
        tooltip=tooltip,
        content=ft.Icon(icon, size=m.icon + 2, color=color),
    )


def star_toggle(m: Metrics, pinned: bool, on_click: Callable) -> ft.Container:
    return icon_action(
        m,
        ft.Icons.STAR if pinned else ft.Icons.STAR_BORDER,
        on_click,
        color=WARNING if pinned else TEXT_FAINT,
        tooltip="Unpin" if pinned else "Pin to home",
    )


# ── page scaffolding ──────────────────────────
def screen(m: Metrics, controls: List[ft.Control], *, scrollable: bool = True) -> ft.Control:
    padding = ft.Padding.only(
        left=m.pad_h, right=m.pad_h, top=m.list_pad_v, bottom=m.list_pad_v
    )

    if scrollable:
        body: ft.Control = ft.ListView(
            expand=True, spacing=m.gap, padding=padding, controls=controls
        )
    else:
        body = ft.Container(
            expand=True,
            padding=padding,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                spacing=m.gap,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=controls,
            ),
        )

    if m.max_content_width:
        # Phones and desktops: a centred column, not a stretched one.
        return ft.Row(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[ft.Container(width=m.max_content_width, content=body)],
        )
    return body


def header(
    m: Metrics,
    text: str,
    on_back: Optional[Callable] = None,
    on_action: Optional[Callable] = None,
    action_icon: str = ft.Icons.REFRESH,
) -> ft.Container:
    controls: List[ft.Control] = []
    if on_back:
        controls.append(icon_action(m, ft.Icons.ARROW_BACK_IOS_NEW, on_back, color=TEXT_DIM))
    controls.append(
        ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Text(
                text,
                size=m.size_title,
                weight=ft.FontWeight.W_600,
                color=TEXT,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                text_align=ft.TextAlign.CENTER,
            ),
        )
    )
    if on_action:
        controls.append(icon_action(m, action_icon, on_action, color=TEXT_DIM))
    elif on_back:
        # Balance the chevron so the title stays optically centred.
        controls.append(ft.Container(width=44))

    return ft.Container(
        padding=ft.Padding.only(bottom=2),
        content=ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controls,
        ),
    )


def status_chip(m: Metrics, connected: bool, label: str, on_tap: Optional[Callable] = None) -> ft.Container:
    """Connection state, one line, always at the top of the home screen."""
    return ft.Container(
        border_radius=20,
        padding=ft.Padding.symmetric(vertical=5, horizontal=m.tile_pad_h),
        bgcolor=ft.Colors.with_opacity(0.10, ACCENT if connected else DANGER),
        ink=on_tap is not None,
        on_click=on_tap,
        content=ft.Row(
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=7, height=7, border_radius=4,
                    bgcolor=ACCENT if connected else DANGER,
                ),
                ft.Text(
                    label,
                    size=m.size_sub,
                    color=TEXT_DIM,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        ),
    )


def empty_state(
    m: Metrics,
    *,
    icon: str,
    heading: str,
    message: str,
    action_label: Optional[str] = None,
    on_action: Optional[Callable] = None,
) -> List[ft.Control]:
    """What a screen shows before it has anything to show."""
    controls: List[ft.Control] = [
        ft.Container(height=m.gap),
        ft.Icon(icon, size=m.icon_large, color=TEXT_FAINT),
        title(m, heading),
        caption(m, message),
    ]
    if action_label and on_action:
        controls.append(ft.Container(height=m.gap))
        controls.append(tile(m, label=action_label, icon=ft.Icons.SEARCH,
                             on_tap=on_action, tone="accent"))
    return controls


# ── overlays ──────────────────────────────────
def _overlay(page: ft.Page, content: ft.Control, m: Metrics, dismissible: bool = False) -> ft.Container:
    """Full-screen scrim with content centred on it."""

    def dismiss(_=None):
        close_overlay(page, holder)

    holder = ft.Container(
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.94, "#000000"),
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding.symmetric(horizontal=m.pad_h, vertical=m.list_pad_v),
        on_click=dismiss if dismissible else None,
        content=content,
    )
    page.overlay.append(holder)
    page.update()
    return holder


def close_overlay(page: ft.Page, holder: ft.Control):
    if holder in page.overlay:
        page.overlay.remove(holder)
        page.update()


def busy(page: ft.Page, m: Metrics, message: str) -> Callable[[], None]:
    """Blocking spinner. Returns the function that takes it away."""
    holder = _overlay(
        page,
        ft.Column(
            spacing=m.gap + 4,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.ProgressRing(width=m.icon_large, height=m.icon_large,
                                stroke_width=3, color=ACCENT),
                ft.Text(message, size=m.size_label, color=TEXT,
                        text_align=ft.TextAlign.CENTER, max_lines=3),
            ],
        ),
        m,
    )
    return lambda: close_overlay(page, holder)


def detail_chip(m: Metrics, text: str) -> ft.Container:
    return ft.Container(
        bgcolor=SURFACE_HIGH,
        border_radius=14,
        padding=ft.Padding.symmetric(vertical=6, horizontal=12),
        content=ft.Text(
            text,
            size=m.size_label,
            weight=ft.FontWeight.W_600,
            color=TEXT,
            text_align=ft.TextAlign.CENTER,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    )


def confirm(
    page: ft.Page,
    m: Metrics,
    *,
    heading: str,
    message: str = "",
    detail: Optional[str] = None,
    confirm_label: str = "Yes",
    on_confirm: Callable,
    tone: str = "accent",
):
    holder: List[ft.Control] = []

    def close(_=None):
        if holder:
            close_overlay(page, holder[0])

    def accept(e=None):
        close()
        on_confirm()

    controls: List[ft.Control] = [
        title(m, heading),
    ]
    if detail:
        controls.append(detail_chip(m, detail))
    if message:
        controls.append(caption(m, message, color=TEXT_FAINT))
    controls.append(ft.Container(height=m.gap))
    controls.append(tile(m, label=confirm_label, icon=ft.Icons.CHECK, on_tap=accept, tone=tone))
    controls.append(tile(m, label="Cancel", icon=ft.Icons.CLOSE, on_tap=close, tone="ghost"))

    holder.append(
        _overlay(
            page,
            ft.Column(
                spacing=m.gap,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
                controls=controls,
            ),
            m,
        )
    )


def menu(page: ft.Page, m: Metrics, heading: str, items: List[tuple],
         subheading: Optional[str] = None):
    holder: List[ft.Control] = []

    def close(_=None):
        if holder:
            close_overlay(page, holder[0])

    def wrap(callback):
        def handler(e=None):
            close()
            callback()
        return handler

    controls: List[ft.Control] = [
        ft.Text(
            heading,
            size=m.size_label,
            weight=ft.FontWeight.W_600,
            color=TEXT,
            text_align=ft.TextAlign.CENTER,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    ]
    if subheading:
        controls.append(
            ft.Text(
                subheading,
                size=m.size_sub,
                color=TEXT_DIM,
                text_align=ft.TextAlign.CENTER,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
    controls.append(ft.Container(height=2))
    for label, icon, callback, tone in items:
        controls.append(tile(m, label=label, icon=icon, on_tap=wrap(callback), tone=tone))
    controls.append(tile(m, label="Close", icon=ft.Icons.CLOSE, on_tap=close, tone="ghost"))

    holder.append(
        _overlay(
            page,
            ft.Column(
                spacing=m.gap,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
                controls=controls,
            ),
            m,
        )
    )


def letter_picker(
    m: Metrics,
    letters: List[str],
    selected: str,
    on_pick: Callable[[str], None],
) -> ft.Control:
    size = 36.0 if m.watch else 42.0

    def cell(letter: str) -> ft.Control:
        active = letter == selected
        return ft.Container(
            width=size,
            height=size,
            border_radius=size / 2,
            alignment=ft.Alignment.CENTER,
            bgcolor=ACCENT if active else SURFACE_HIGH,
            ink=True,
            on_click=lambda e, value=letter: on_pick("" if active else value),
            content=ft.Text(
                letter,
                size=m.size_label,
                weight=ft.FontWeight.W_600,
                color=ON_ACCENT if active else TEXT,
            ),
        )

    return ft.Container(
        padding=ft.Padding.only(bottom=m.gap),
        content=ft.Row(
            wrap=True,
            spacing=4,
            run_spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[cell(letter) for letter in letters],
        ),
    )


#: Six columns of six: the 26 letters and 10 digits, no dead cells.
KEYPAD_ROWS = ("ABCDEF", "GHIJKL", "MNOPQR", "STUVWX", "YZ0123", "456789")


def keypad(
    page: ft.Page,
    m: Metrics,
    *,
    initial: str = "",
    on_done: Callable[[str], None],
    heading: str = "Filter",
):
    """A full-screen text entry surface with its own keys.

    Wear OS is the reason this exists. A watch cannot be relied on to raise a
    soft keyboard for an inline field — on some devices the IME never appears
    at all — so this borrows the shape the platform's own apps use: you press
    search, you get a dedicated input screen, and it owns both the text and the
    keys. Nothing here depends on the system IME.

    The typed text is handed back only when Done is pressed, so a half-typed
    word never filters the list underneath.
    """
    state = {"value": initial}
    holder: List[ft.Control] = []

    # The full 36-key grid needs more height than a watch face has, so only the
    # keys scroll: what you have typed and the Done key stay put. Losing sight
    # of either while reaching for Z would be worse than the scroll itself.
    display = ft.Container(alignment=ft.Alignment.CENTER)
    keys = ft.Column(
        spacing=3,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    actions = ft.Container(alignment=ft.Alignment.CENTER)

    def close(_=None):
        if holder:
            close_overlay(page, holder[0])

    def accept(_=None):
        close()
        on_done(state["value"])

    def press(char: str):
        state["value"] += char
        render()

    def backspace(_=None):
        state["value"] = state["value"][:-1]
        render()

    def clear(_=None):
        state["value"] = ""
        render()

    # Keys sit closer to the edge than normal content: a keyboard needs the
    # width more than it needs a comfortable margin.
    columns = len(KEYPAD_ROWS[0])
    spacing = 3.0
    # Fill the width on a watch, but stop at a sensible key on a big screen —
    # a 60px letter is a button, not a keyboard.
    size = min(44.0, max(24.0, (max(120.0, m.width - m.pad_h) - spacing * (columns - 1)) / columns))
    usable = size * columns + spacing * (columns - 1)

    def key(char: str) -> ft.Control:
        return ft.Container(
            width=size,
            height=size,
            border_radius=size / 4,
            alignment=ft.Alignment.CENTER,
            bgcolor=SURFACE_HIGH,
            ink=True,
            on_click=lambda e, c=char: press(c),
            content=ft.Text(char, size=m.size_label, weight=ft.FontWeight.W_600, color=TEXT),
        )

    def action(icon: str, handler: Callable, tone: str = "raised") -> ft.Control:
        background, foreground, _ = TONES.get(tone, TONES["raised"])
        return ft.Container(
            width=size + 6,
            height=size,
            border_radius=size / 4,
            alignment=ft.Alignment.CENTER,
            bgcolor=background,
            ink=True,
            on_click=handler,
            content=ft.Icon(icon, size=m.icon, color=foreground),
        )

    def render():
        typed = state["value"]
        display.content = ft.Column(
            spacing=1,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(heading, size=m.size_small, color=TEXT_FAINT,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Container(
                    width=usable,
                    bgcolor=SURFACE,
                    border_radius=10,
                    padding=ft.Padding.symmetric(vertical=5, horizontal=10),
                    content=ft.Text(
                        typed or "…",
                        size=m.size_label,
                        weight=ft.FontWeight.W_600,
                        color=TEXT if typed else TEXT_FAINT,
                        text_align=ft.TextAlign.CENTER,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ),
            ],
        )

        keys.controls = [
            ft.Row(
                spacing=spacing,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[key(char) for char in row],
            )
            for row in KEYPAD_ROWS
        ]

        actions.content = ft.Row(
            spacing=spacing,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                action(ft.Icons.BACKSPACE_OUTLINED, backspace),
                action(ft.Icons.SPACE_BAR, lambda e: press(" ")),
                action(ft.Icons.CLOSE, clear),
                action(ft.Icons.CHECK, accept, tone="accent"),
            ],
        )
        page.update()

    render()
    holder.append(
        ft.Container(
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.97, "#000000"),
            padding=ft.Padding.symmetric(horizontal=m.pad_h / 2, vertical=6),
            content=ft.Column(
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[display, keys, actions],
            ),
        )
    )
    page.overlay.append(holder[0])
    page.update()


def toast(page: ft.Page, m: Metrics, message: str, tone: str = "surface", seconds: float = 2.0):
    bg, fg, _ = TONES.get(tone, TONES["surface"])

    holder = ft.Container(
        expand=True,
        alignment=ft.Alignment.BOTTOM_CENTER,
        padding=ft.Padding.only(
            left=m.pad_h, right=m.pad_h, bottom=m.list_pad_v + 4
        ),
        content=ft.Container(
            bgcolor=bg or SURFACE_HIGH,
            border_radius=20,
            padding=ft.Padding.symmetric(vertical=8, horizontal=14),
            content=ft.Text(
                message,
                size=m.size_sub,
                color=fg,
                text_align=ft.TextAlign.CENTER,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ),
    )
    page.overlay.append(holder)
    page.update()

    async def _expire():
        await asyncio.sleep(seconds)
        close_overlay(page, holder)

    page.run_task(_expire)
