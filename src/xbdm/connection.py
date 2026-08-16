import re
import socket
from typing import Optional

from xbdm.exceptions import XbdmConnectionError

XBDM_PORT = 730

_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9\-\.]{0,61}[A-Za-z0-9])?$")


def normalize_host(host: Optional[str]) -> str:
    """Validate a user-typed address, returning it stripped.

    Accepts an IPv4 address or a hostname — some setups reach the console by
    mDNS/router name rather than a raw IP, and rejecting those would be an
    annoying thing to discover on a watch keyboard.
    """
    value = (host or "").strip()
    if not value:
        raise XbdmConnectionError("No console address given")

    if _IPV4_RE.match(value):
        if all(0 <= int(part) <= 255 for part in value.split(".")):
            return value
        raise XbdmConnectionError(f"{value} is not a valid IP address")

    if _HOSTNAME_RE.match(value):
        return value

    raise XbdmConnectionError(f"{value} is not a valid address")


class XbdmConnection:
    RECV_BUFSIZE = 0x10000  # 64 KB — plenty for a dirlist reply

    def __init__(self, host: str, port: int = XBDM_PORT, timeout: float = 6.0):
        self.host = normalize_host(host)
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._buf = b""

    @property
    def is_connected(self) -> bool:
        """True if the socket still looks alive.

        Peeks with the socket temporarily non-blocking: an empty read means the
        console closed the link (which it does on every magicboot), while
        BlockingIOError just means "nothing waiting", i.e. healthy.
        """
        if self.sock is None:
            return False
        try:
            self.sock.setblocking(False)
            try:
                if self.sock.recv(1, socket.MSG_PEEK) == b"":
                    return False
            except BlockingIOError:
                pass
            except (OSError, ConnectionError):
                return False
            finally:
                self.sock.setblocking(True)
                self.sock.settimeout(self.timeout)
            return True
        except Exception:
            return False

    def connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), self.timeout)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as e:
            raise XbdmConnectionError(str(e)) from e
        self._buf = b""

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self._buf = b""

    def send(self, data: bytes):
        if not self.sock:
            raise XbdmConnectionError("Not connected")
        try:
            self.sock.sendall(data)
        except OSError as e:
            raise XbdmConnectionError(str(e)) from e

    def _fill(self):
        try:
            chunk = self.sock.recv(self.RECV_BUFSIZE)
        except socket.timeout as e:
            raise XbdmConnectionError("Console timed out") from e
        except OSError as e:
            raise XbdmConnectionError(str(e)) from e
        if not chunk:
            raise XbdmConnectionError("Connection closed by console")
        self._buf += chunk

    def recv_exact(self, size: int) -> bytes:
        """Read exactly *size* bytes — for binary replies, which carry no
        terminator and must be consumed to the byte or the next command reads
        the tail of this one."""
        if not self.sock:
            raise XbdmConnectionError("Not connected")
        while len(self._buf) < size:
            self._fill()
        data, self._buf = self._buf[:size], self._buf[size:]
        return data

    def recv_line(self) -> bytes:
        if not self.sock:
            raise XbdmConnectionError("Not connected")
        while b"\n" not in self._buf:
            self._fill()
        idx = self._buf.index(b"\n") + 1
        line, self._buf = self._buf[:idx], self._buf[idx:]
        return line
