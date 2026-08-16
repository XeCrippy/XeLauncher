import re
import threading
from typing import List, Optional

from xbdm.connection import XbdmConnection
from xbdm.exceptions import XbdmCommandError, XbdmConnectionError, XbdmError
from xbdm.protocol import parse_response_line

LAUNCHABLE_EXTS = (".xex", ".xbe", ".exe")


class XbdmClient:
    def __init__(self, host: str, timeout: float = 6.0):
        self.host = host
        self.timeout = timeout
        self.conn = XbdmConnection(host, timeout=timeout)
        self._lock = threading.RLock()
        #: Set after a magicboot: the console tears the socket down as it
        #: switches titles, and nothing should be sent until it is back.
        self.booting = False

    # ── lifecycle ─────────────────────────────
    def connect(self) -> "XbdmClient":
        with self._lock:
            self.conn.connect()
            # xbdm greets every new socket with "201- connected"; consume it so
            # the first real command reads its own reply.
            parse_response_line(self.conn.recv_line())
            self.booting = False
            return self

    def close(self):
        with self._lock:
            try:
                self.conn.send(b"bye\r\n")
            except Exception:
                pass
            self.conn.close()

    def _ensure_connected(self):
        """Reopen the socket if it died. Caller must hold the lock."""
        if self.conn.is_connected:
            return
        self.conn.close()
        self.conn = XbdmConnection(self.host, timeout=self.timeout)
        self.conn.connect()
        parse_response_line(self.conn.recv_line())
        self.booting = False

    def is_alive(self) -> bool:
        """Cheap liveness check — used by the status chip, never fatal."""
        try:
            with self._lock:
                self._ensure_connected()
                self.send_command("dbgname")
            return True
        except XbdmError:
            return False

    # ── raw command plumbing ──────────────────
    def send_command(self, command: str):
        with self._lock:
            self._ensure_connected()
            self.conn.send(command.encode() + b"\r\n")
            return parse_response_line(self.conn.recv_line())

    def send_multiline_command(self, command: str) -> List[str]:
        with self._lock:
            self._ensure_connected()
            self.conn.send(command.encode() + b"\r\n")
            response = parse_response_line(self.conn.recv_line())

            lines: List[str] = []
            if response.multiline:
                while True:
                    line = self.conn.recv_line().decode("ascii", errors="replace").strip()
                    if line == ".":
                        break
                    lines.append(line)
            return lines

    # ── console identity ──────────────────────
    def console_name(self) -> str:
        return self.send_command("dbgname").message.strip()

    def current_title_path(self) -> Optional[str]:
        try:
            lines = self.send_multiline_command("xbeinfo name=")
        except XbdmError:
            return None

        for line in lines:
            if line.startswith("name="):
                value = line[len("name="):].strip().strip('"')
                return value or None
        return None

    # ── filesystem ────────────────────────────
    def get_drive_list(self) -> List[str]:
        """Drive names as ``HDD:\\``, ``USB0:\\`` … ready to use as paths."""
        drives = []
        for line in self.send_multiline_command("drivelist"):
            match = re.search(r'drivename="([^"]+)"', line)
            if match:
                name = match.group(1)
                drives.append(name if name.endswith(":\\") else f"{name}:\\")
        return drives

    def get_directory_contents(self, remote_path: str) -> List[dict]:
        """List one folder.

        Each xbdm line looks like::

            name="default.xex" sizehi=0x0 sizelo=0x4000 createhi=... changelo=...
            name="Halo 3" sizehi=0x0 sizelo=0x0 ... directory

        Only the fields a launcher uses are parsed — name, size and whether it
        is a folder. Timestamps are skipped on purpose: nothing on a watch
        screen has room to show them.
        """
        entries = []
        for line in self.send_multiline_command(f'dirlist name="{remote_path}"'):
            match = re.search(r'name="([^"]+)"', line)
            if not match:
                continue

            entry = {"name": match.group(1), "is_directory": "directory" in line}

            size_hi = re.search(r"sizehi=0x([0-9a-fA-F]+)", line)
            size_lo = re.search(r"sizelo=0x([0-9a-fA-F]+)", line)
            if size_hi and size_lo:
                entry["size"] = (int(size_hi.group(1), 16) << 32) | int(size_lo.group(1), 16)

            entries.append(entry)
        return entries

    # ── partial file reads ────────────────────
    def read_file_range(self, remote_path: str, offset: int, size: int) -> Optional[bytes]:
        """Read *size* bytes from *offset* of a file on the console.

        ``getfile`` takes ``offset`` and ``size`` (not ``length`` — xbdm answers
        ``400- missing size`` for that), which is what makes reading a title ID
        out of a 20 MB game viable: the header is a few hundred bytes and the
        rest never crosses the network.

        The reply is ``203- binary response follows``, then a little-endian
        u32 length, then that many raw bytes. Returns None if the console
        refuses the read rather than raising, because a missing or locked file
        is an ordinary outcome when walking a stranger's drive.
        """
        with self._lock:
            self._ensure_connected()
            self.conn.send(
                f'getfile name="{remote_path}" offset={offset} size={size}\r\n'.encode()
            )
            line = self.conn.recv_line()
            if not line.startswith(b"203-"):
                # Consume the status line only; nothing binary follows a 4xx.
                return None
            length = int.from_bytes(self.conn.recv_exact(4), "little")
            if length <= 0:
                return b""
            return self.conn.recv_exact(length)

    # ── boot commands ─────────────────────────
    def _boot(self, command: str):
        with self._lock:
            try:
                self.send_command(command)
            except XbdmConnectionError:
                pass
            except XbdmCommandError:
                self.conn.close()
                raise
            finally:
                # Either way the console is on its way somewhere else.
                self.conn.close()
                self.booting = True

    def launch(self, path: str, directory: Optional[str] = None):
        target = path.strip().rstrip("\\\r\n")
        if directory is None:
            directory = target.rsplit("\\", 1)[0] if "\\" in target else target
        directory = directory.rstrip("\\")
        self._boot(f'magicboot title="{target}" directory="{directory}"')

    def goto_dashboard(self):
        self._boot("magicboot")

    def reboot(self, cold: bool = True):
        self._boot("magicboot cold" if cold else "magicboot warm")

    def shutdown(self):
        command = 'consolefeatures ver=2 type=11 params="A\\0\\A\\0\\"'
        with self._lock:
            try:
                self.send_command(command)
            except XbdmConnectionError:
                # A successful shutdown can cut the socket before its reply.
                pass
            except XbdmCommandError:
                self.conn.close()
                raise
            finally:
                self.conn.close()


def connect(host: str, timeout: float = 6.0) -> XbdmClient:
    """Open a client, or raise :class:`XbdmError` trying."""
    return XbdmClient(host, timeout=timeout).connect()


def try_connect(host: str, timeout: float = 6.0) -> Optional[XbdmClient]:
    """Same, but None instead of an exception — for auto-connect on startup."""
    try:
        return connect(host, timeout=timeout)
    except XbdmError:
        return None


__all__ = [
    "XbdmClient",
    "LAUNCHABLE_EXTS",
    "connect",
    "try_connect",
]
