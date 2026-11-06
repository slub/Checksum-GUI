"""Streaming checksum calculation, independent of the user interface."""

import hashlib
import os
from pathlib import Path
from typing import Callable


class Cancelled(Exception):
    """The user cancelled the operation."""


def checksum_file(
    path: Path, algorithm: str = "sha512", cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int], None] | None = None,
) -> str:
    if algorithm not in ("sha1", "md5", "sha512"):
        raise ValueError(f"Unsupported checksum algorithm: {algorithm}")
    digest = hashlib.new(algorithm, usedforsecurity=False)
    with path.open("rb") as stream:
        total = os.fstat(stream.fileno()).st_size
        processed = last_percent = 0
        while True:
            if cancelled():
                raise Cancelled()
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            processed += len(chunk)
            percent = min(99, processed * 100 // total) if total else 0
            if progress is not None and percent != last_percent:
                progress(percent)
                last_percent = percent
    if progress is not None:
        progress(100)
    return digest.hexdigest()
