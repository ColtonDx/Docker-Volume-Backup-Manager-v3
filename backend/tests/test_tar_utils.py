import io
import tarfile

import pytest

from app.services.tar_utils import UnsafeArchiveError, append_volume, split_archive


def _write_tar(path, members, mode="w"):
    """Write *members* ((TarInfo, bytes | None) pairs) to a tar at *path*."""
    with tarfile.open(path, mode) as tar:
        for info, data in members:
            if data is not None:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.addfile(info)
    return str(path)


def _file(name, data=b"x", **attrs):
    info = tarfile.TarInfo(name)
    for key, value in attrs.items():
        setattr(info, key, value)
    return info, data


def _entry(name, type_, linkname="", **attrs):
    info = tarfile.TarInfo(name)
    info.type = type_
    info.linkname = linkname
    for key, value in attrs.items():
        setattr(info, key, value)
    return info, None


def _read(path):
    """{name: (TarInfo, bytes | None)} for every member of a tar."""
    out = {}
    with tarfile.open(path) as tar:
        for m in tar:
            fh = tar.extractfile(m) if m.isreg() else None
            out[m.name] = (m, fh.read() if fh else None)
    return out


# ----------------------------------------------------------------------
# append_volume: Docker export -> backup archive
# ----------------------------------------------------------------------

def test_append_volume_reroots_and_keeps_metadata(tmp_path):
    """Everything a volume can hold goes into the archive unaltered but the path.

    The previous implementation extracted through tarfile's data filter, which
    refused absolute symlinks outright (failing the whole volume) and dropped
    ownership and setuid bits from everything else.
    """
    export = _write_tar(tmp_path / "export.tar", [
        _entry(".", tarfile.DIRTYPE, mode=0o700, uid=999, gid=999),
        _file("./db/data", b"rows", mode=0o4750, uid=999, gid=998),
        _entry("./abs", tarfile.SYMTYPE, "/cryptpad/src/tweetnacl"),
        _entry("./hard", tarfile.LNKTYPE, "./db/data"),
        _entry("./pipe", tarfile.FIFOTYPE),
        _file("./" + "d" * 150 + "/long.txt", b"long"),
    ])

    archive = tmp_path / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as out:
        append_volume(out, export, "vol")

    members = _read(archive)
    root = members["vol"][0]
    assert root.isdir() and root.mode == 0o700 and root.uid == 999

    data, body = members["vol/db/data"]
    assert body == b"rows"
    assert (data.mode, data.uid, data.gid) == (0o4750, 999, 998)

    assert members["vol/abs"][0].linkname == "/cryptpad/src/tweetnacl"
    assert members["vol/hard"][0].linkname == "vol/db/data"
    assert members["vol/pipe"][0].isfifo()
    # Long names are stored in a PAX header; the rename must win over it.
    assert "vol/" + "d" * 150 + "/long.txt" in members


# ----------------------------------------------------------------------
# split_archive: backup archive -> one tar per volume
# ----------------------------------------------------------------------

def test_split_archive_separates_volumes_and_keeps_metadata(tmp_path):
    archive = _write_tar(tmp_path / "b.tar.gz", [
        _entry("a", tarfile.DIRTYPE, mode=0o700, uid=999),
        _file("a/f.txt", b"alpha", uid=999, mode=0o600),
        _entry("a/abs", tarfile.SYMTYPE, "/etc/hostname"),
        _entry("a/hard", tarfile.LNKTYPE, "a/f.txt"),
        _entry("b", tarfile.DIRTYPE),
        _file("b/g.txt", b"bravo"),
    ], mode="w:gz")

    split = split_archive(archive, str(tmp_path), None)
    assert set(split.volumes) == {"a", "b"}

    a = _read(split.volumes["a"])
    assert split.roots["a"] == (999, 0, 0o700)
    assert a["f.txt"][1] == b"alpha" and a["f.txt"][0].uid == 999
    assert a["abs"][0].linkname == "/etc/hostname"
    assert a["hard"][0].linkname == "f.txt"
    assert _read(split.volumes["b"])["g.txt"][1] == b"bravo"


def test_split_archive_skips_volumes_not_wanted(tmp_path):
    archive = _write_tar(tmp_path / "b.tar", [
        _file("mine/f", b"1"),
        _file("bystander/f", b"2"),
    ])
    split = split_archive(archive, str(tmp_path), {"mine"})
    assert list(split.volumes) == ["mine"]
    assert split.unexpected == ["bystander"]


def test_split_archive_skips_device_nodes(tmp_path):
    archive = _write_tar(tmp_path / "b.tar", [
        _file("v/f", b"1"),
        _entry("v/dev", tarfile.CHRTYPE),
    ])
    split = split_archive(archive, str(tmp_path), None)
    assert split.skipped == ["v/dev"]
    assert "dev" not in _read(split.volumes["v"])


@pytest.mark.parametrize("members", [
    pytest.param([_file("../escape")], id="parent-traversal"),
    pytest.param([_file("v/../../escape")], id="nested-traversal"),
    pytest.param([_file("/etc/evil")], id="absolute-path"),
    pytest.param([_file("-bad name/f")], id="invalid-volume-name"),
    pytest.param([_entry("v", tarfile.SYMTYPE, "/")], id="volume-root-is-symlink"),
    pytest.param([_entry("v/h", tarfile.LNKTYPE, "other/f")], id="hardlink-other-volume"),
    pytest.param([_entry("v/h", tarfile.LNKTYPE, "/etc/passwd")], id="hardlink-absolute"),
    pytest.param([_entry("v/h", tarfile.LNKTYPE, "v/../../x")], id="hardlink-traversal"),
    pytest.param(
        [_entry("v/link", tarfile.SYMTYPE, "/etc"), _file("v/link/passwd")],
        id="write-through-symlink",
    ),
])
def test_split_archive_rejects_unsafe_members(tmp_path, members):
    archive = _write_tar(tmp_path / "evil.tar", [_file("v/ok", b"fine"), *members])
    with pytest.raises(UnsafeArchiveError):
        split_archive(archive, str(tmp_path), None)
