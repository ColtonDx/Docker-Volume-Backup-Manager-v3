"""Safe tar extraction helpers.

Guards against path-traversal / Zip-Slip: archive members whose paths (or link
targets) escape the destination directory via absolute paths, ".." segments, or
symlink chains.
"""

from __future__ import annotations

import tarfile


def safe_extractall(tar: tarfile.TarFile, dest: str) -> None:
    """Extract every member of *tar* into *dest*, blocking unsafe members.

    Uses tarfile's built-in 'data' filter (PEP 706), which refuses absolute
    paths, ".." traversal, and links that point outside the destination — the
    cases a naive extractall would happily follow.
    """
    try:
        tar.extractall(path=dest, filter="data")
    except TypeError:
        # Python < 3.12 lacks the filter argument. Fail closed rather than fall
        # back to an unfiltered (unsafe) extraction.
        raise RuntimeError(
            "Safe tar extraction requires Python 3.12+ (tarfile data filter)."
        )
