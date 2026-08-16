from dataclasses import dataclass

import flet as ft

# ── palette ───────────────────────────────────
ACCENT = "#15A551"
ACCENT_DEEP = "#129147"
ACCENT_SOFT = "#1E6B43"

BG_WATCH = "#000000"
BG_WIDE = "#131313"
SURFACE = "#1C1C1C"
SURFACE_HIGH = "#282828"

TEXT = "#F0F2F1"
TEXT_DIM = "#9BA09D"
TEXT_FAINT = "#6E736F"

DANGER = "#D8556A"
WARNING = "#E0A93A"
ON_ACCENT = "#062012"

#: Below this width we are on a watch, not a phone.
WATCH_MAX_WIDTH = 300
#: Phones and desktops get a centred column rather than a stretched one.
CONTENT_MAX_WIDTH = 460


@dataclass(frozen=True)
class Metrics:
    """Every size the UI needs, resolved once per layout."""

    width: float
    watch: bool
    round_screen: bool

    pad_h: float
    list_pad_v: float
    gap: float

    tile_height: float
    tile_radius: float
    tile_pad_h: float

    size_title: float
    size_label: float
    size_sub: float
    size_small: float
    icon: float
    icon_large: float

    @property
    def bg(self) -> str:
        return BG_WATCH if self.watch else BG_WIDE

    @property
    def max_content_width(self) -> float | None:
        return None if self.watch else CONTENT_MAX_WIDTH


def metrics_for(page: ft.Page, round_screen: bool = True) -> Metrics:
    width = float(page.width or 200)
    watch = width < WATCH_MAX_WIDTH

    if watch:
        # On a round face the usable width is the inscribed square, so keep
        # roughly a tenth of the diameter clear on each side.
        pad_h = max(12.0, width * 0.10) if round_screen else 8.0
        return Metrics(
            width=width,
            watch=True,
            round_screen=round_screen,
            pad_h=pad_h,
            list_pad_v=28.0 if round_screen else 12.0,
            gap=6.0,
            tile_height=50.0,
            tile_radius=25.0,
            tile_pad_h=12.0,
            size_title=15.0,
            size_label=13.5,
            size_sub=11.0,
            size_small=10.0,
            icon=18.0,
            icon_large=34.0,
        )

    return Metrics(
        width=width,
        watch=False,
        round_screen=False,
        pad_h=18.0,
        list_pad_v=14.0,
        gap=10.0,
        tile_height=62.0,
        tile_radius=18.0,
        tile_pad_h=16.0,
        size_title=21.0,
        size_label=16.0,
        size_sub=12.5,
        size_small=11.5,
        icon=22.0,
        icon_large=44.0,
    )


def app_theme() -> ft.Theme:
    return ft.Theme(
        color_scheme_seed=ACCENT,
        color_scheme=ft.ColorScheme(
            primary=ACCENT,
            on_primary=ON_ACCENT,
            surface=SURFACE,
            on_surface=TEXT,
            error=DANGER,
        ),
    )
