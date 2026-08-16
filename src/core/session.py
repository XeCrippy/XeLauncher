import threading
from typing import Dict, List, Optional, Tuple

from xbdm import XbdmClient, XbdmError, connect as xbdm_connect
from core.titles import label_for


class Session:
    def __init__(self):
        self.client: Optional[XbdmClient] = None
        self.host: str = ""
        self.console_name: str = ""
        self.error: str = ""
        self._lock = threading.RLock()

    # ── connection ────────────────────────────
    @property
    def connected(self) -> bool:
        return self.client is not None

    def connect(self, host: str) -> Tuple[bool, str]:
        """Open a connection. Returns ``(ok, message)``."""
        with self._lock:
            self.disconnect()
            try:
                client = xbdm_connect(host)
                name = ""
                try:
                    name = client.console_name()
                except XbdmError:
                    pass
                self.client = client
                self.host = host
                self.console_name = name or host
                self.error = ""
                return True, self.console_name
            except XbdmError as ex:
                self.client = None
                self.error = ex.friendly
                return False, ex.friendly
            except Exception as ex:
                # Connecting must never raise into a screen: a bad address or
                # a resolver failure is a message on the connect screen, not a
                # crash on the user's wrist.
                self.client = None
                self.error = str(ex) or "Could not connect"
                return False, self.error

    def disconnect(self):
        with self._lock:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.client = None
            self.console_name = ""

    def ensure(self) -> Tuple[bool, str]:
        """Reconnect to the remembered host if the link went away."""
        with self._lock:
            if self.client and self.client.is_alive():
                return True, self.console_name
            if not self.host:
                return False, "No console"
            return self.connect(self.host)

    # ── console info ──────────────────────────
    def current_title(self) -> Optional[Dict[str, str]]:
        """What is running right now, labeled — or None on the dashboard."""
        with self._lock:
            if not self.client:
                return None
            try:
                path = self.client.current_title_path()
            except XbdmError:
                return None

        if not path:
            return None

        directory, _, filename = path.rstrip("\\").rpartition("\\")
        name = label_for(directory or path, filename or path)
        if filename.lower() in ("xshell.xex", "dash.xex") or not directory:
            return None
        return {"name": name, "path": path}

    def read_range(self, path: str, offset: int, size: int) -> Optional[bytes]:
        """Read part of a file on the console, or None if it cannot be read.

        Used to pull a title ID out of a game's XEX header without dragging
        the whole executable across the network. Never raises: a locked or
        missing file is an ordinary thing to meet while browsing.
        """
        with self._lock:
            if not self.client:
                return None
            try:
                return self.client.read_file_range(path, offset, size)
            except XbdmError:
                return None
            except Exception:
                return None

    def drives(self) -> List[str]:
        with self._lock:
            if not self.client:
                return []
            try:
                return self.client.get_drive_list()
            except XbdmError:
                return []

    # ── actions ───────────────────────────────
    def launch(self, entry: Dict) -> Tuple[bool, str]:
        ok, message = self.ensure()
        if not ok:
            return False, message

        with self._lock:
            try:
                self.client.launch(entry["path"], entry.get("dir") or None)
                return True, entry.get("name", "Game")
            except XbdmError as ex:
                return False, ex.friendly

    def goto_dashboard(self) -> Tuple[bool, str]:
        ok, message = self.ensure()
        if not ok:
            return False, message
        with self._lock:
            try:
                self.client.goto_dashboard()
                return True, "Returning to dashboard"
            except XbdmError as ex:
                return False, ex.friendly

    def reboot(self) -> Tuple[bool, str]:
        ok, message = self.ensure()
        if not ok:
            return False, message
        with self._lock:
            try:
                self.client.reboot(cold=True)
                return True, "Rebooting console"
            except XbdmError as ex:
                return False, ex.friendly

    def shutdown(self) -> Tuple[bool, str]:
        ok, message = self.ensure()
        if not ok:
            return False, message
        with self._lock:
            try:
                self.client.shutdown()
                self.client = None
                self.console_name = ""
                return True, "Shutting down console"
            except XbdmError as ex:
                return False, ex.friendly
