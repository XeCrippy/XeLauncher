from xbdm.exceptions import XbdmCommandError


class XbdmResponse:
    __slots__ = ("code", "message")

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message

    @property
    def ok(self) -> bool:
        return 200 <= self.code < 300

    @property
    def multiline(self) -> bool:
        return self.code == 202

    def __repr__(self) -> str:
        return f"XbdmResponse({self.code}, {self.message!r})"


def parse_response_line(line: bytes, raise_on_error: bool = True) -> XbdmResponse:
    """Turn one raw reply line into a response, raising on 4xx by default."""
    text = line.decode("ascii", errors="ignore").strip()
    if len(text) < 3 or not text[:3].isdigit():
        raise XbdmCommandError(0, f"Unreadable reply from console: {text[:40]!r}")

    code = int(text[:3])
    message = text[4:].strip()

    if code >= 400 and raise_on_error:
        raise XbdmCommandError.from_code(code, message)

    return XbdmResponse(code, message)
