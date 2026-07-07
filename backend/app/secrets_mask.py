"""Masking of secret values in API responses.

GET endpoints return configuration objects that contain credentials (storage
secret keys, SMTP/FTP passwords, webhook URLs, API tokens, the raw rclone
config). These are replaced with a sentinel on read; on write, a field left at
the sentinel means "unchanged" and the stored value is preserved. This keeps
secrets out of API responses without forcing the operator to re-enter them on
every edit.

Note: the configuration *export* endpoint intentionally keeps real values —
they are required to restore a working configuration and the export is an
explicit, authenticated action.
"""

from __future__ import annotations

from typing import Any

SENTINEL = "********"

# Field names treated as secret wherever they appear in a config dict, plus the
# secret-bearing keys in the flat settings bundle (raw rclone config text).
SECRET_KEYS: frozenset[str] = frozenset({
    "secret_access_key",   # S3
    "password",            # FTP / SFTP
    "smtp_password",       # email
    "app_token",           # gotify
    "access_token",        # ntfy
    "webhook_url",         # slack / discord
    "rclone_config_text",  # settings bundle
    "rclone_config_inline",  # settings bundle (alias)
})


def mask_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *config* with non-empty secret fields replaced by the sentinel."""
    masked = dict(config)
    for key in SECRET_KEYS:
        value = masked.get(key)
        if isinstance(value, str) and value != "":
            masked[key] = SENTINEL
    return masked


def unmask_config(new_config: dict[str, Any], old_config: dict[str, Any]) -> dict[str, Any]:
    """Merge *new_config* over *old_config*, treating a sentinel as "unchanged".

    For each secret field whose incoming value is the sentinel, keep the old
    stored value (or drop the field entirely if there is nothing to preserve),
    so the literal sentinel is never written to storage.
    """
    merged = dict(new_config)
    for key in SECRET_KEYS:
        if merged.get(key) == SENTINEL:
            if old_config.get(key) is not None:
                merged[key] = old_config[key]
            else:
                merged.pop(key, None)
    return merged
