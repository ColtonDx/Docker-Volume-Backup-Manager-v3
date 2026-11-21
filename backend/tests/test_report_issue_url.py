"""REPORT_ISSUE_URL: default, override, and empty (hidden) behaviour."""

from app.config import DEFAULT_REPORT_ISSUE_URL, get_report_issue_url


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("REPORT_ISSUE_URL", raising=False)
    assert get_report_issue_url() == DEFAULT_REPORT_ISSUE_URL
    assert DEFAULT_REPORT_ISSUE_URL.startswith("https://github.com/ColtonDx/")


def test_override(monkeypatch):
    monkeypatch.setenv("REPORT_ISSUE_URL", " https://example.com/issues/new ")
    assert get_report_issue_url() == "https://example.com/issues/new"


def test_empty_hides_link(monkeypatch):
    monkeypatch.setenv("REPORT_ISSUE_URL", "")
    assert get_report_issue_url() == ""
    monkeypatch.setenv("REPORT_ISSUE_URL", "   ")
    assert get_report_issue_url() == ""


def test_health_exposes_value(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("REPORT_ISSUE_URL", "https://example.com/x")
    # No lifespan context: health must still carry the field even if degraded.
    res = TestClient(app).get("/api/health")
    assert res.json()["report_issue_url"] == "https://example.com/x"
