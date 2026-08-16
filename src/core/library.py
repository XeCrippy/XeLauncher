import os
from typing import Dict, List, Optional

from core.titles import basename, label_for, title_name, variant_label
from xbdm.client import LAUNCHABLE_EXTS, XbdmClient


def is_launchable(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in LAUNCHABLE_EXTS


def join(*parts: str) -> str:
    return "\\".join(p.rstrip("\\") for p in parts if p)


def normalize_dir_path(path: str) -> str:
    cleaned = (path or "").strip()
    return f"{cleaned}\\" if cleaned.endswith(":") else cleaned


def parent_of(path: str) -> Optional[str]:
    """The folder above, or None at a drive root."""
    cleaned = (path or "").rstrip("\\")
    parent, separator, _ = cleaned.rpartition("\\")
    if not separator or not parent:
        return None
    return normalize_dir_path(parent)


# ── listing ───────────────────────────────────
def drive_entries(client: XbdmClient) -> List[Dict]:
    return [
        {
            "name": drive.rstrip("\\"),
            "label": drive.rstrip("\\"),
            "path": normalize_dir_path(drive),
            "is_directory": True,
        }
        for drive in client.get_drive_list()
    ]


def list_directory(client: XbdmClient, path: str) -> Dict:
    path = normalize_dir_path(path)
    folders: List[Dict] = []
    files: List[Dict] = []
    hidden = 0

    for entry in client.get_directory_contents(path):
        name = entry.get("name", "")
        if not name:
            continue

        if entry.get("is_directory"):
            folders.append(
                {
                    "name": name,
                    "label": folder_label(name),
                    "path": join(path, name),
                    "is_directory": True,
                }
            )
        elif is_launchable(name):
            files.append(file_entry(path, name, entry.get("size", 0)))
        else:
            hidden += 1

    folders.sort(key=lambda e: e["label"].lower())
    files.sort(key=lambda e: e["file"].lower())
    return {"path": path, "folders": folders, "files": files, "hidden": hidden}


def folder_label(name: str) -> str:
    return title_name(name) or name


def file_entry(directory: str, filename: str, size: int = 0) -> Dict:
    return {
        "name": label_for(directory, filename),
        "path": join(directory, filename),
        "dir": directory.rstrip("\\"),
        "file": filename,
        "drive": directory.split(":", 1)[0].upper(),
        "size": int(size or 0),
    }


def entry_for_path(path: str) -> Dict:
    normalized = path.strip().rstrip("\\")
    directory, _, filename = normalized.rpartition("\\")
    return file_entry(directory or normalized, filename or normalized)


# ── display ───────────────────────────────────
def file_display(entry: Dict, siblings: bool = False) -> tuple:
    filename = entry.get("file") or basename(entry.get("path", ""))

    if siblings:
        return (variant_label(filename) or filename), filename

    return (entry.get("name") or filename), filename


def initial_of(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    first = cleaned[0].upper()
    return first if first.isalpha() else "#"


def listing_initials(listing: Dict) -> List[str]:
    found = set()
    for folder in listing.get("folders", []):
        found.add(initial_of(folder.get("label") or folder.get("name")))
    for entry in listing.get("files", []):
        found.add(initial_of(entry.get("name") or entry.get("file")))
    found.discard("")
    # "#" last: letters are what people look for first.
    letters = sorted(f for f in found if f != "#")
    return letters + (["#"] if "#" in found else [])


def filter_listing(listing: Dict, query: str = "", initial: str = "") -> tuple:
    needle = (query or "").strip().lower()
    letter = (initial or "").strip().upper()

    folders = listing.get("folders", [])
    files = listing.get("files", [])

    if letter:
        folders = [f for f in folders
                   if initial_of(f.get("label") or f.get("name")) == letter]
        files = [f for f in files
                 if initial_of(f.get("name") or f.get("file")) == letter]

    if needle:
        def hit(*values) -> bool:
            return any(needle in (v or "").lower() for v in values)

        folders = [f for f in folders if hit(f.get("label"), f.get("name"))]
        files = [f for f in files if hit(f.get("name"), f.get("file"))]

    return folders, files


def filename_is_informative(entry: Dict) -> bool:
    filename = (entry.get("file") or "").lower()
    if not filename:
        return False
    stem = os.path.splitext(filename)[0]
    return stem != "default" and stem != "game"


__all__ = [
    "is_launchable",
    "join",
    "normalize_dir_path",
    "parent_of",
    "drive_entries",
    "list_directory",
    "folder_label",
    "file_entry",
    "entry_for_path",
    "file_display",
    "filter_listing",
    "initial_of",
    "listing_initials",
    "filename_is_informative",
]
