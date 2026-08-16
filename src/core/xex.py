"""Reading a title ID out of an Xbox 360 executable.

The title ID is the key to everything cosmetic: it is what turns a folder
called ``BF3`` into *Battlefield 3* and fetches its cover. Matching folder
names against the title database only resolves about half of a real console —
scene folders are abbreviated, misspelled and full of extra words — while the
ID inside the XEX is exact and always right.

XEX2 layout, all big-endian (the 360 is PowerPC)::

    0x00  'XEX2'
    0x14  optional header count
    0x18  count × (key u32, value u32)

The entry with key ``0x00040006`` is the execution info block, and the title ID
sits 12 bytes into it. That block usually lives around 0x2900 — past any
sensible first read — so this is done in two ranged reads: a few hundred bytes
for the header table, then 16 bytes at the offset it points to. About half a
kilobyte per game, rather than the whole 20 MB.
"""

import struct
from typing import Callable, Optional

#: XEX_HEADER_EXECUTION_INFO
EXECUTION_INFO_KEY = 0x00040006

#: Title ID's offset within the execution info block.
TITLE_ID_OFFSET = 0x0C

#: Enough for the optional header table: a real XEX has ~15 entries, so the
#: table ends well inside 512 bytes.
HEADER_READ_SIZE = 512

#: Sanity ceiling. A corrupt or non-XEX file must not send us walking off the
#: end of the buffer looking for hundreds of headers.
MAX_OPTIONAL_HEADERS = 64


def execution_info_offset(header: bytes) -> Optional[int]:
    """Where the execution info block lives, or None if this is not a XEX2."""
    if len(header) < 0x18 or header[:4] != b"XEX2":
        return None

    count = struct.unpack(">I", header[0x14:0x18])[0]
    if count > MAX_OPTIONAL_HEADERS:
        return None

    for index in range(count):
        end = 0x20 + index * 8
        if end > len(header):
            break
        key, value = struct.unpack(">II", header[end - 8:end])
        if key == EXECUTION_INFO_KEY:
            return value
    return None


def title_id_from_block(block: bytes) -> Optional[int]:
    """Pull the title ID out of an execution info block."""
    if len(block) < TITLE_ID_OFFSET + 4:
        return None
    title_id = struct.unpack(">I", block[TITLE_ID_OFFSET:TITLE_ID_OFFSET + 4])[0]
    return title_id or None


def read_title_id(read_range: Callable[[int, int], Optional[bytes]]) -> Optional[int]:
    """Resolve a title ID given a ranged reader for one file.

    *read_range* is ``(offset, size) -> bytes | None``; keeping the transport
    behind a callable is what lets this be tested against a synthetic XEX with
    no console and no sockets involved.
    """
    header = read_range(0, HEADER_READ_SIZE)
    if not header:
        return None

    offset = execution_info_offset(header)
    if offset is None:
        return None

    # Occasionally the block is already inside the header read; skip the second
    # round trip when it is.
    end = offset + TITLE_ID_OFFSET + 4
    if end <= len(header):
        return title_id_from_block(header[offset:end])

    block = read_range(offset, 0x10)
    if not block:
        return None
    return title_id_from_block(block)


def format_title_id(title_id: int) -> str:
    """``0x4D5307E6`` → ``4D5307E6`` — the form every art URL wants."""
    return f"{title_id:08X}"
