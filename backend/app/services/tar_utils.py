"""Tar helpers for moving volume contents in and out of backup archives.

Volume data is never extracted onto DVBM's own filesystem. Extracting it would
have to run through a safety filter, and any filter strict enough to be safe
here also refuses or rewrites legitimate volume contents: absolute symlinks
(common in application images), FIFOs, file ownership and setuid bits. Instead
tar members are copied header-for-header between archives, and the only place
anything is written to disk is inside the volume itself, by the Docker daemon.

A backup archive holds one top-level directory per volume:

    <volume name>/
    <volume name>/path/inside/the/volume
"""

from __future__ import annotations

import os
import re
import tarfile
from dataclasses import dataclass, field

# Docker's own rule for volume names. Anything else at the top level of an
# archive cannot be a volume DVBM wrote, so it is treated as tampering.
_VOLUME_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class UnsafeArchiveError(Exception):
    """An archive member that must not be restored."""


def _parts(name: str) -> list[str]:
    """Split a member path into components, dropping '' and '.'."""
    return [p for p in name.split("/") if p not in ("", ".")]


def _copy_member(src: tarfile.TarFile, member: tarfile.TarInfo, out: tarfile.TarFile,
                 name: str, linkname: str | None = None) -> None:
    """Write *member* to *out* under a new name, keeping every other attribute."""
    member.name = name
    if linkname is not None:
        member.linkname = linkname
    # A PAX path/linkpath header takes priority over the name fields when the
    # member is written, so a stale one would silently undo the rename.
    member.pax_headers.pop("path", None)
    member.pax_headers.pop("linkpath", None)
    out.addfile(member, src.extractfile(member) if member.isreg() else None)


def append_volume(out: tarfile.TarFile, volume_tar: str, volume_name: str) -> None:
    """Copy a volume export (Docker ``get_archive`` output) into a backup archive.

    Members are re-rooted under ``<volume_name>/``. Symlink targets are kept
    verbatim: they are resolved inside the application's container, not here.
    """
    with tarfile.open(volume_tar, "r") as src:
        for member in src:
            rel = "/".join(_parts(member.name))
            name = f"{volume_name}/{rel}" if rel else volume_name
            linkname = None
            if member.islnk():
                # Hard link targets are archive paths, so they move with the rename.
                linkname = f"{volume_name}/{'/'.join(_parts(member.linkname))}"
            _copy_member(src, member, out, name, linkname)


@dataclass
class SplitArchive:
    """The result of :func:`split_archive`."""

    # volume name -> path of a tar holding that volume's contents, rooted at "."
    volumes: dict[str, str] = field(default_factory=dict)
    # top-level volumes present in the archive but not requested
    unexpected: list[str] = field(default_factory=list)
    # device nodes and other unsupported entries that were left out
    skipped: list[str] = field(default_factory=list)
    # volume name -> (uid, gid, mode) of the volume's root directory
    roots: dict[str, tuple[int, int, int]] = field(default_factory=dict)


def split_archive(archive_path: str, dest_dir: str, wanted: set[str] | None) -> SplitArchive:
    """Split a backup archive into one tar per volume, ready for ``put_archive``.

    Only volumes in *wanted* are kept (all of them when *wanted* is None). The
    archive may come from remote storage, so it is treated as untrusted: any
    absolute path, ``..`` component, invalid volume name, hard link leaving its
    volume, or member placed beneath a symlink raises UnsafeArchiveError. The
    whole archive is checked before the caller touches any volume.
    """
    result = SplitArchive()
    outputs: dict[str, tarfile.TarFile] = {}
    symlinks: dict[str, set[str]] = {}

    try:
        with tarfile.open(archive_path, "r:*") as src:
            for member in src:
                if member.name.startswith("/"):
                    raise UnsafeArchiveError(f"absolute path in archive: {member.name!r}")
                parts = _parts(member.name)
                if ".." in parts:
                    raise UnsafeArchiveError(f"path traversal in archive: {member.name!r}")
                if not parts:
                    continue
                volume, rel = parts[0], parts[1:]
                if not _VOLUME_NAME.match(volume):
                    raise UnsafeArchiveError(f"invalid volume name in archive: {volume!r}")

                if wanted is not None and volume not in wanted:
                    if volume not in result.unexpected:
                        result.unexpected.append(volume)
                    continue

                if not rel:
                    if not member.isdir():
                        raise UnsafeArchiveError(f"volume root is not a directory: {member.name!r}")
                    # put_archive does not apply the "." entry to the directory
                    # it extracts into, so the caller has to.
                    result.roots[volume] = (member.uid, member.gid, member.mode & 0o7777)

                # A member beneath a symlink would be written through it, to
                # wherever the link points.
                links = symlinks.setdefault(volume, set())
                for i in range(1, len(rel)):
                    if "/".join(rel[:i]) in links:
                        raise UnsafeArchiveError(f"member beneath a symlink: {member.name!r}")

                linkname = None
                if member.islnk():
                    target = _parts(member.linkname)
                    if (member.linkname.startswith("/") or ".." in target
                            or len(target) < 2 or target[0] != volume):
                        raise UnsafeArchiveError(
                            f"hard link leaves its volume: {member.name!r} -> {member.linkname!r}"
                        )
                    linkname = "/".join(target[1:])
                elif member.issym():
                    links.add("/".join(rel))
                elif not (member.isreg() or member.isdir() or member.isfifo()):
                    # Device nodes and anything else exotic.
                    result.skipped.append(member.name)
                    continue

                out = outputs.get(volume)
                if out is None:
                    path = os.path.join(dest_dir, f"{volume}.tar")
                    out = outputs[volume] = tarfile.open(path, "w")
                    result.volumes[volume] = path
                _copy_member(src, member, out, "/".join(rel) or ".", linkname)
    finally:
        for out in outputs.values():
            out.close()

    return result
