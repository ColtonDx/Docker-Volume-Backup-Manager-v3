"""Helpers for the rclone config file and its relationship to the stored setting.

The config can come from two places: text saved in Settings (stored in the
database and written to disk) or a file mounted into the container. These
helpers keep the two from silently overwriting each other.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

TEXT_KEYS = ("rclone_config_inline", "rclone_config_text")


def config_text_from(settings_dict: dict[str, Any]) -> str:
    """Return the stripped rclone config text in a settings dict ("" if none)."""
    for key in TEXT_KEYS:
        val = settings_dict.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def config_path_from(settings_dict: dict[str, Any] | None = None) -> Path:
    """Resolve the config file path (settings override, else the env default)."""
    custom = (settings_dict or {}).get("rclone_config_path")
    return Path(custom if isinstance(custom, str) and custom else app_settings.RCLONE_CONFIG)


def read_config(path: Path) -> str | None:
    """Return the stripped file content, or None if it is missing/unreadable."""
    try:
        if not path.is_file():
            return None
        return path.read_text(errors="replace").strip()
    except OSError:
        return None


def list_remotes(config_path: str | Path | None = None) -> dict[str, Any]:
    """List configured rclone remote names via `rclone listremotes`."""
    path = str(config_path or app_settings.RCLONE_CONFIG)
    try:
        result = subprocess.run(
            [app_settings.RCLONE_BINARY, "listremotes", "--config", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"remotes": [], "error": result.stderr.strip()}
        # Each line is "remotename:", strip the colon
        remotes = [line.rstrip(":").strip() for line in result.stdout.strip().splitlines() if line.strip()]
        return {"remotes": remotes}
    except FileNotFoundError:
        return {"remotes": [], "error": "rclone binary not found"}
    except Exception as exc:
        return {"remotes": [], "error": str(exc)}


def get_status(stored: dict[str, Any]) -> dict[str, Any]:
    """Describe the rclone config. Never includes file contents or secrets."""
    path = config_path_from(stored)
    db_text = config_text_from(stored)
    file_text = read_config(path)
    exists = file_text is not None
    if db_text:
        source = "ui"
    elif exists:
        source = "file"
    else:
        source = "none"

    mtime = None
    remotes: list[str] = []
    error = None
    if exists:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass
        listed = list_remotes(path)
        remotes = listed.get("remotes", [])
        error = listed.get("error")

    return {
        "config_path": str(path),
        "file_exists": exists,
        "source": source,
        # True when a file is present that newly saved text would replace
        # (there is no saved text, or the file differs from it).
        "file_differs_from_saved": bool(exists and file_text != db_text),
        "remotes": remotes,
        "error": error,
        "modified": mtime,
    }


def plan_write(path: Path, new_text: str, old_text: str) -> str:
    """Decide what to do when saving *new_text* over the file at *path*.

    Returns "write", "skip" (leave the file alone) or "confirm" (the file looks
    hand-managed; replacing it needs explicit confirmation).
    """
    file_text = read_config(path)
    if file_text is None:
        return "write"
    if file_text == new_text:
        return "skip"
    if new_text == old_text:
        # Saved text is unchanged; the differing file belongs to someone else.
        return "skip"
    if file_text == old_text:
        # The file is exactly what was last written from Settings, so
        # replacing it is safe.
        return "write"
    return "confirm"


def write_config(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.strip() + "\n")
        logger.info("Rclone config written to %s (%d bytes)", path, len(text))
        return True
    except Exception as exc:
        logger.error("Failed to write rclone config to %s: %s", path, exc)
        return False
