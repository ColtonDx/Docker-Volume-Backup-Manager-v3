import io
import tarfile

import pytest

from app.services.tar_utils import safe_extractall


def _tar_with(members) -> io.BytesIO:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for add in members:
            add(tar)
    buf.seek(0)
    return buf


def _add_file(name: str, data: bytes = b"x"):
    def _add(tar):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return _add


def test_safe_archive_extracts(tmp_path):
    buf = _tar_with([_add_file("ok/file.txt", b"hi")])
    with tarfile.open(fileobj=buf) as tar:
        safe_extractall(tar, str(tmp_path))
    assert (tmp_path / "ok" / "file.txt").read_bytes() == b"hi"


def test_absolute_path_does_not_escape(tmp_path):
    # The data filter neutralizes an absolute member by stripping the leading
    # slash and extracting it *inside* dest, rather than writing to the root.
    import os

    buf = _tar_with([_add_file("/etc/evil_dvbm_test")])
    with tarfile.open(fileobj=buf) as tar:
        safe_extractall(tar, str(tmp_path))
    assert not os.path.exists("/etc/evil_dvbm_test")
    assert (tmp_path / "etc" / "evil_dvbm_test").exists()


def test_parent_traversal_blocked(tmp_path):
    buf = _tar_with([_add_file("../evil_dvbm_test")])
    with tarfile.open(fileobj=buf) as tar:
        with pytest.raises(Exception):
            safe_extractall(tar, str(tmp_path))
    assert not (tmp_path.parent / "evil_dvbm_test").exists()


def test_escaping_symlink_blocked(tmp_path):
    def _add_symlink(tar):
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)

    buf = _tar_with([_add_symlink])
    with tarfile.open(fileobj=buf) as tar:
        with pytest.raises(Exception):
            safe_extractall(tar, str(tmp_path))
