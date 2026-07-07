import pytest

from app.services.storage_service import StorageService


def test_parses_quoted_flags():
    assert StorageService._rclone_extra_flags(
        {"flags": "--transfers=4 --bwlimit '1M'"}
    ) == ["--transfers=4", "--bwlimit", "1M"]


def test_empty_flags():
    assert StorageService._rclone_extra_flags({}) == []
    assert StorageService._rclone_extra_flags({"flags": "   "}) == []


@pytest.mark.parametrize("bad", ["--config /etc/x.conf", "--config=/etc/x.conf", "--CONFIG y"])
def test_config_override_blocked(bad):
    with pytest.raises(ValueError):
        StorageService._rclone_extra_flags({"flags": bad})


def test_invalid_quoting_rejected():
    with pytest.raises(ValueError):
        StorageService._rclone_extra_flags({"flags": "--x 'unterminated"})
