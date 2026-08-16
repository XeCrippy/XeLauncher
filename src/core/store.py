import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

SRC_DIR = Path(__file__).resolve().parents[1]


def _is_android() -> bool:
    return os.name == "posix" and "ANDROID_ROOT" in os.environ


def _is_writable(directory: str) -> bool:
    try:
        os.makedirs(directory, exist_ok=True)
        probe = os.path.join(directory, ".xelauncher-write-test")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


class Store:
    FILE_NAME = "xelauncher.json"

    def __init__(self):
        # ── connection ────────────────────────
        self.host: str = ""
        self.auto_connect: bool = True

        # ── content ───────────────────────────
        self.favorites: List[Dict[str, Any]] = []

        # ── preferences ───────────────────────
        self.confirm_launch: bool = False
        #: Round watch faces clip the corners; this widens the side margins.
        self.round_screen: bool = True
        #: Show cover art on game tiles. The only feature that reaches the
        #: internet, so it is one toggle away from off.
        self.box_art: bool = True

        self.last_error: str = ""
        self._resolved_dir: Optional[str] = None

        self.load()

    # ── paths ─────────────────────────────────

    def data_dir(self) -> str:
        if self._resolved_dir is None:
            self._resolved_dir = self._resolve_dir()
        return self._resolved_dir

    def _candidate_dirs(self) -> List[str]:
        candidates: List[str] = []

        def add(value):
            if value and value not in candidates:
                candidates.append(str(value))

        add(os.environ.get("FLET_APP_STORAGE_DATA"))

        if _is_android():
            add(os.environ.get("FLET_APP_STORAGE_TEMP"))
            home = os.path.expanduser("~")
            if home and home != "~":
                add(os.path.join(home, "xelauncher"))
        else:
            add(str(SRC_DIR / "storage" / "data"))
            home = os.path.expanduser("~")
            if home and home != "~":
                add(os.path.join(home, ".xelauncher"))

        add(os.path.join(tempfile.gettempdir(), "xelauncher"))
        return candidates

    def _resolve_dir(self) -> str:
        candidates = self._candidate_dirs()

        for candidate in candidates:
            if os.path.isfile(os.path.join(candidate, self.FILE_NAME)) and _is_writable(candidate):
                return candidate

        for candidate in candidates:
            if _is_writable(candidate):
                return candidate

        return candidates[0] if candidates else tempfile.gettempdir()

    def use_directory(self, directory: str) -> bool:
        if not directory or not _is_writable(directory):
            return False

        previous = self.data_dir()
        if os.path.normpath(previous) == os.path.normpath(directory):
            return True

        self._resolved_dir = directory
        target = self.path()
        if not os.path.isfile(target):
            source = os.path.join(previous, self.FILE_NAME)
            if os.path.isfile(source):
                try:
                    shutil.copyfile(source, target)
                except OSError:
                    pass
        self.load()
        return True

    def path(self) -> str:
        return os.path.join(self.data_dir(), self.FILE_NAME)

    def storage_status(self) -> str:
        if self.last_error:
            return f"Not saving: {self.last_error}"
        return self.data_dir()

    # ── load / save ───────────────────────────
    def load(self):
        try:
            target = self.path()
            if not os.path.isfile(target):
                return
            with open(target, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self._apply(data)
        except Exception:
            pass

    def _apply(self, data: dict):
        host = data.get("host")
        if isinstance(host, str):
            self.host = host.strip()

        for flag in ("auto_connect", "confirm_launch", "round_screen", "box_art"):
            if isinstance(data.get(flag), bool):
                setattr(self, flag, data[flag])

        self.favorites = [e for e in data.get("favorites", []) if _valid_entry(e)]

    def save(self) -> bool:
        """Write settings. Records why on failure — never fails silently."""
        payload = {
            "host": self.host,
            "auto_connect": self.auto_connect,
            "favorites": self.favorites,
            "confirm_launch": self.confirm_launch,
            "round_screen": self.round_screen,
            "box_art": self.box_art,
        }
        try:
            os.makedirs(self.data_dir(), exist_ok=True)
            temp_path = f"{self.path()}.tmp"
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(temp_path, self.path())
            self.last_error = ""
            return True
        except Exception as ex:
            self.last_error = f"{type(ex).__name__}: {ex}"[:120]
            return False

    # ── console ───────────────────────────────
    def set_host(self, host: str):
        self.host = (host or "").strip()
        self.save()

    def forget_host(self):
        self.host = ""
        self.save()

    # ── favorites ─────────────────────────────
    def is_favorite(self, path: str) -> bool:
        key = path.lower()
        return any(entry["path"].lower() == key for entry in self.favorites)

    def add_favorite(self, entry: Dict[str, Any]) -> bool:
        if not _valid_entry(entry) or self.is_favorite(entry["path"]):
            return False
        self.favorites.append(dict(entry))
        self.save()
        return True

    def remove_favorite(self, path: str) -> bool:
        key = path.lower()
        before = len(self.favorites)
        self.favorites = [e for e in self.favorites if e["path"].lower() != key]
        if len(self.favorites) == before:
            return False
        self.save()
        return True

    def toggle_favorite(self, entry: Dict[str, Any]) -> bool:
        """Pin or unpin. Returns True if it is now pinned."""
        if self.is_favorite(entry["path"]):
            self.remove_favorite(entry["path"])
            return False
        self.add_favorite(entry)
        return True

    def move_favorite(self, path: str, delta: int) -> bool:
        key = path.lower()
        for index, entry in enumerate(self.favorites):
            if entry["path"].lower() != key:
                continue
            target = index + delta
            if not 0 <= target < len(self.favorites):
                return False
            self.favorites[index], self.favorites[target] = (
                self.favorites[target],
                self.favorites[index],
            )
            self.save()
            return True
        return False

    def clear_favorites(self):
        self.favorites = []
        self.save()


def _valid_entry(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and isinstance(entry.get("name"), str)
        and bool(entry["path"])
    )
