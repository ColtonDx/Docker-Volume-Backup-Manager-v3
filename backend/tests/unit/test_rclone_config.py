"""Rclone config status endpoint and overwrite protection."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.config import settings
from app.database import SessionLocal, init_db
from app.main import _sync_rclone_config_on_startup, app
from app.models import Setting
from app.services import rclone_config

MOUNTED = "[mounted]\ntype = s3\nsecret_access_key = SUPERSECRET-MOUNTED\n"
SAVED = "[uiremote]\ntype = s3\nsecret_access_key = SUPERSECRET-UI\n"
OTHER = "[other]\ntype = s3\nsecret_access_key = SUPERSECRET-OTHER\n"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    init_db()
    path = tmp_path / "rclone.conf"
    monkeypatch.setattr(settings, "RCLONE_CONFIG", str(path))
    # No rclone binary in the unit environment: fake the remote listing by
    # parsing section headers, as `rclone listremotes` would.
    def fake_list(config_path=None):
        text = rclone_config.read_config(Path(str(config_path))) or ""
        return {"remotes": [ln[1:-1] for ln in text.splitlines() if ln.startswith("[")]}
    monkeypatch.setattr(rclone_config, "list_remotes", fake_list)

    db = SessionLocal()
    db.query(Setting).delete()
    db.commit()
    db.close()

    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token()}"
    yield client, path
    db = SessionLocal()
    db.query(Setting).delete()
    db.commit()
    db.close()


def _save(client, text, **extra):
    return client.put("/api/settings", json={"settings": {"rclone_config_inline": text}, **extra})


def test_status_requires_auth():
    assert TestClient(app).get("/api/settings/rclone/status").status_code in (401, 403)


def test_status_none(env):
    client, _ = env
    body = client.get("/api/settings/rclone/status").json()
    assert body["source"] == "none"
    assert body["file_exists"] is False
    assert body["remotes"] == []


def test_status_file_never_leaks_contents(env):
    client, path = env
    path.write_text(MOUNTED)
    res = client.get("/api/settings/rclone/status")
    body = res.json()
    assert body["source"] == "file"
    assert body["file_exists"] is True
    assert body["config_path"] == str(path)
    assert body["remotes"] == ["mounted"]
    assert body["modified"]
    assert "SUPERSECRET" not in res.text


def test_status_ui_source(env):
    client, path = env
    assert _save(client, SAVED).status_code == 200
    res = client.get("/api/settings/rclone/status")
    body = res.json()
    assert body["source"] == "ui"
    assert body["file_differs_from_saved"] is False
    assert "SUPERSECRET" not in res.text


def test_save_writes_when_no_file(env):
    client, path = env
    assert _save(client, SAVED).status_code == 200
    assert path.read_text().strip() == SAVED.strip()


def test_ui_user_can_edit_own_config(env):
    client, path = env
    _save(client, SAVED)
    assert _save(client, OTHER).status_code == 200
    assert path.read_text().strip() == OTHER.strip()


def test_save_refuses_to_clobber_mounted_file(env):
    client, path = env
    path.write_text(MOUNTED)
    res = _save(client, SAVED)
    assert res.status_code == 409
    assert path.read_text() == MOUNTED
    # nothing was persisted either
    assert client.get("/api/settings/rclone/status").json()["source"] == "file"


def test_save_overwrites_when_confirmed(env):
    client, path = env
    path.write_text(MOUNTED)
    assert _save(client, SAVED, overwrite_rclone_config=True).status_code == 200
    assert path.read_text().strip() == SAVED.strip()


def test_unchanged_resave_keeps_diverged_file(env):
    client, path = env
    _save(client, SAVED)
    path.write_text(MOUNTED)  # file replaced behind our back
    # The UI re-sends the masked sentinel for unchanged text.
    res = client.put("/api/settings", json={"settings": {"rclone_config_inline": "********", "timezone": "UTC"}})
    assert res.status_code == 200
    assert path.read_text() == MOUNTED


def test_startup_does_not_overwrite_existing_file(env):
    client, path = env
    _save(client, SAVED)
    path.write_text(MOUNTED)
    _sync_rclone_config_on_startup()
    assert path.read_text() == MOUNTED


def test_startup_recreates_missing_file(env):
    client, path = env
    _save(client, SAVED)
    path.unlink()
    _sync_rclone_config_on_startup()
    assert path.read_text().strip() == SAVED.strip()


def _zip_with_settings(settings_dict):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("settings.json", json.dumps(settings_dict))
    return buf.getvalue()


def test_import_does_not_clobber_without_confirmation(env):
    client, path = env
    path.write_text(MOUNTED)
    data = _zip_with_settings({"rclone_config_inline": SAVED})
    res = client.post("/api/settings/import", files={"file": ("c.zip", data, "application/zip")})
    assert res.status_code == 200
    assert res.json()["imported"].get("rclone_config_skipped") is True
    assert path.read_text() == MOUNTED


def test_import_overwrites_when_confirmed(env):
    client, path = env
    path.write_text(MOUNTED)
    data = _zip_with_settings({"rclone_config_inline": SAVED})
    res = client.post(
        "/api/settings/import?overwrite_rclone_config=true",
        files={"file": ("c.zip", data, "application/zip")},
    )
    assert res.status_code == 200
    assert path.read_text().strip() == SAVED.strip()
