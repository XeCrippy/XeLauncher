import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Callable, List, Optional

from xbdm.connection import XBDM_PORT

#: A watch CPU is not a desktop; 64 sockets in flight sweeps a /24 in a few
#: seconds without thrashing.
MAX_WORKERS = 64
PROBE_TIMEOUT = 0.75


class XbdmDiscoveryError(Exception):
    """Raised when the sweep cannot even start (no network, no subnet)."""


def local_ip() -> Optional[str]:
    """This device's LAN address, via a UDP socket that never sends anything."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1.0)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


def subnet_prefix() -> Optional[str]:
    """``192.168.1`` for a device on 192.168.1.x — the manual-entry prefill.

    Typing a full IP on a watch is miserable; knowing the first three octets
    means the user only has to enter the last one.
    """
    ip = local_ip()
    if not ip:
        return None
    return ip.rsplit(".", 1)[0]


def subnet_hosts(ip: str) -> List[str]:
    try:
        network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
        return [str(host) for host in network.hosts()]
    except ValueError:
        return []


def is_xbdm(ip: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """True if something on *ip* greets us with an xbdm banner.

    xbdm answers a fresh connection with ``201- connected``. Anything else
    listening on 730 is not a console, so the banner is checked rather than
    just the open port.
    """
    try:
        with socket.create_connection((ip, XBDM_PORT), timeout=timeout) as sock:
            sock.settimeout(timeout)
            banner = sock.recv(128)
            return b"201-" in banner or b"connected" in banner.lower()
    except Exception:
        return False


def find_consoles(
    on_found: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    stop: Optional[Event] = None,
    first_only: bool = False,
) -> List[str]:
    """Sweep the local /24 for consoles.

    *on_found* fires per console as it is discovered, *on_progress* fires with
    ``(done, total)`` so a determinate ring can be drawn, and *stop* aborts the
    sweep between probes. Both callbacks run on worker threads — marshal them
    onto Flet's loop before touching UI.
    """
    ip = local_ip()
    if not ip:
        raise XbdmDiscoveryError("This device is not on a network")

    hosts = subnet_hosts(ip)
    if not hosts:
        raise XbdmDiscoveryError("Could not work out the local subnet")

    found: List[str] = []
    total = len(hosts)
    done = 0
    stop = stop or Event()

    def probe(target: str) -> Optional[str]:
        if stop.is_set():
            return None
        return target if is_xbdm(target) else None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for result in pool.map(probe, hosts):
            done += 1
            if on_progress:
                on_progress(done, total)
            if result:
                found.append(result)
                if on_found:
                    on_found(result)
                if first_only:
                    stop.set()
                    break
            if stop.is_set() and not first_only:
                break

    return found
