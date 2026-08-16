import os
import re

from core.title_ids import TITLE_IDS

GENERIC_FILENAMES = {"default.xex", "default.xbe", "game.xex"}

VARIANT_NAMES = {
    "": "Campaign",
    "mp": "Multiplayer",
    "sp": "Campaign",
    "zm": "Zombies",
    "zombies": "Zombies",
    "coop": "Co-op",
}

#: Trailing junk that shows up in scene folder names and wastes screen width.
_NOISE = re.compile(
    r"\s*[\(\[\{](?:usa|eur|jpn|pal|ntsc|ntsc-u|ntsc-j|region\s*free|rf|xbla|"
    r"dlc|tu\d*|v?\d+\.\d+[\w.]*|disc\s*\d+)[\)\]\}]\s*",
    re.IGNORECASE,
)


def basename(path: str) -> str:
    return path.rstrip("\\").replace("/", "\\").rsplit("\\", 1)[-1]


def title_name(text: str) -> str | None:
    candidate = text.strip()
    if len(candidate) != 8:
        return None
    try:
        return TITLE_IDS.get(int(candidate, 16))
    except ValueError:
        return None


def tidy(name: str) -> str:
    cleaned = name.replace("_", " ")
    if " " not in cleaned and cleaned.count(".") >= 2:
        cleaned = cleaned.replace(".", " ")
    cleaned = _NOISE.sub(" ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -–—")
    return cleaned or name


def is_default_family(filename: str) -> bool:
    stem = os.path.splitext(filename)[0]
    return stem.lower().startswith("default")


def variant_label(filename: str) -> str:
    """``default_mp.xex`` → "Multiplayer" — what one entry point is *for*.

    A folder with several executables labels each by its role rather than
    repeating the game name on every row.
    """
    stem = os.path.splitext(filename)[0]
    lowered = stem.lower()
    if not lowered.startswith("default"):
        return tidy(stem)

    suffix = lowered[len("default"):].strip("_- ")
    if suffix in VARIANT_NAMES:
        return VARIANT_NAMES[suffix]
    return suffix.upper() if suffix else "Campaign"


def label_for(directory: str, filename: str) -> str:
    """Best display name for one launchable file.

    ``HDD:\\Games\\Halo 3\\default.xex``      → "Halo 3"
    ``HDD:\\Content\\...\\4D5307E6\\x.xex``   → "Fallout 3"
    ``HDD:\\Apps\\XeXMenu 1.1\\xexmenu.xex``  → "XeXMenu 1.1"
    ``USB0:\\Emus\\snes360\\alt.xex``         → "snes360 — alt"
    """
    folder = basename(directory) or directory.rstrip("\\:")
    stem = os.path.splitext(filename)[0]

    if folder.endswith(":"):
        return title_name(stem) or tidy(stem)

    folder_title = title_name(folder)
    if folder_title:
        base = folder_title
    else:
        base = tidy(folder)

    if filename.lower() in GENERIC_FILENAMES:
        return base

    if is_default_family(filename):
        return f"{base} — {variant_label(filename)}"

    file_title = title_name(stem)
    if file_title:
        return file_title

    file_label = tidy(stem)
    if file_label.lower() == base.lower():
        return base
    return f"{base} — {file_label}"


def drive_label(path: str) -> str:
    """``HDD:\\Games\\Halo 3`` → ``HDD`` — the sublabel on a game tile."""
    head = path.split(":", 1)[0]
    return head.upper() if head else path
