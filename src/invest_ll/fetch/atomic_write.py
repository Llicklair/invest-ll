"""Write a data file so that nobody ever reads it half-written.

The panel can update its data in the background while it keeps serving (`api/datos.py`): writing
`klines_1d.parquet` in place meant a request arriving mid-write read a truncated file and failed
("Couldn't deserialize thrift"). Writing to a temporary file next to the target and moving it into
place in one step means readers see the old file or the new one, never a mix, and a crash halfway
through no longer destroys the file that was there.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from pathlib import Path

ATTEMPTS: Final = 40
PAUSE: Final = 0.25
"""Windows cannot replace a file another process (or thread) has open: retry for ~10 s."""


def replace_atomically(
    destination: Path,
    write: Callable[[Path], object],
    *,
    attempts: int = ATTEMPTS,
    pause: float = PAUSE,
) -> None:
    """Call `write(temporary)` and move the result onto `destination` in one step."""
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        write(temporary)
        for attempt in range(attempts):
            try:
                temporary.replace(destination)  # os.replace: one step, also on Windows
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(pause)
    finally:
        temporary.unlink(missing_ok=True)
