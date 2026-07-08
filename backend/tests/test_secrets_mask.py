from app.secrets_mask import SENTINEL, mask_config, unmask_config


def test_mask_hides_secrets_keeps_others():
    cfg = {"bucket": "b", "access_key_id": "AKIA", "secret_access_key": "shh", "region": "us"}
    masked = mask_config(cfg)
    assert masked["secret_access_key"] == SENTINEL
    assert masked["access_key_id"] == "AKIA"
    assert masked["bucket"] == "b"
    # original is not mutated
    assert cfg["secret_access_key"] == "shh"


def test_mask_leaves_empty_secret_empty():
    assert mask_config({"password": ""})["password"] == ""


def test_unmask_preserves_sentinel_value():
    old = {"secret_access_key": "realkey", "bucket": "b"}
    new = {"secret_access_key": SENTINEL, "bucket": "b2"}
    merged = unmask_config(new, old)
    assert merged["secret_access_key"] == "realkey"
    assert merged["bucket"] == "b2"


def test_unmask_stores_new_secret():
    merged = unmask_config({"secret_access_key": "newkey"}, {"secret_access_key": "old"})
    assert merged["secret_access_key"] == "newkey"


def test_unmask_never_persists_sentinel_without_old():
    merged = unmask_config({"password": SENTINEL}, {})
    assert "password" not in merged


def test_settings_rclone_text_is_masked():
    assert mask_config({"rclone_config_text": "[r]\nkey=abc"})["rclone_config_text"] == SENTINEL
