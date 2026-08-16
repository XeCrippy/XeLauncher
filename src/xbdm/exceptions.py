from typing import Dict, Optional, Type


class XbdmError(Exception):
    """Base for everything this package raises."""

    @property
    def friendly(self) -> str:
        return str(self) or "Something went wrong"


class XbdmConnectionError(XbdmError):
    """Socket-level failure: refused, timed out, or dropped mid-command."""

    @property
    def friendly(self) -> str:
        text = str(self).lower()
        if "timed out" in text or "timeout" in text:
            return "Console did not answer"
        if "refused" in text:
            return "Console refused the connection"
        if "closed" in text or "reset" in text:
            return "Connection dropped"
        return "Cannot reach console"


class XbdmCommandError(XbdmError):
    """The console answered, but with a 4xx status."""

    code: Optional[int] = None
    _registry: Dict[int, Type["XbdmCommandError"]] = {}

    def __init_subclass__(cls, code: Optional[int] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if code is not None:
            cls.code = code
            XbdmCommandError._registry[code] = cls

    def __init__(self, code: Optional[int] = None, message: str = ""):
        self.code = code if code is not None else type(self).code
        self.message = message
        super().__init__(f"{self.code} {message}".strip())

    @classmethod
    def from_code(cls, code: int, message: str = "") -> "XbdmCommandError":
        return cls._registry.get(code, cls)(code, message)

    @property
    def friendly(self) -> str:
        return _FRIENDLY.get(self.code or 0, self.message or "Console rejected that")


class XbdmMaxConnectionsError(XbdmCommandError, code=401):
    """401 — xbdm allows only a handful of sockets at once.

    Very reachable here: a desktop client and the watch each hold a connection,
    and a stale one left by a crashed app counts too.
    """


class XbdmFileNotFoundError(XbdmCommandError, code=402):
    """402 — the path is gone (drive unplugged, game deleted, typo)."""


class XbdmUnknownCommandError(XbdmCommandError, code=407):
    """407 — xbdm build does not know this command."""


class XbdmAccessDeniedError(XbdmCommandError, code=414):
    """414 — access denied."""


#: Wrist-sized wording for the codes a launcher can realistically provoke.
_FRIENDLY = {
    400: "Console had an unexpected error",
    401: "Too many apps connected to the console",
    402: "That file is no longer on the console",
    403: "No such module",
    404: "Memory not mapped",
    407: "Console does not support that command",
    410: "That file already exists",
    411: "Folder is not empty",
    412: "Invalid file name",
    413: "File could not be created",
    414: "Access denied by the console",
    415: "No room left on the device",
    416: "Console is not debuggable",
    418: "Console has no data for that",
    421: "Key exchange required",
    422: "A dedicated connection is required",
}
