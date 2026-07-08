"""SSRF-guard tests. Import notification_service (requires httpx from requirements)."""

import pytest

from app.services.notification_service import _validate_outbound_url


@pytest.mark.parametrize("url", [
    "https://ntfy.sh/topic",
    "http://192.168.1.50:8080/hook",   # private LAN allowed
    "https://10.0.0.5",
    "http://172.16.3.4/x",
])
def test_public_and_lan_allowed(url):
    _validate_outbound_url(url)  # must not raise


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://169.254.169.254",
    "https://[fe80::1]/x",                        # IPv6 link-local
])
def test_metadata_and_linklocal_blocked(url):
    with pytest.raises(ValueError):
        _validate_outbound_url(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x", "ftp://host/x", ""])
def test_non_http_schemes_blocked(url):
    with pytest.raises(ValueError):
        _validate_outbound_url(url)
