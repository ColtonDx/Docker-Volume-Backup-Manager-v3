"""Test configuration.

Sets deterministic environment variables before any application module is
imported (config, auth, database all read these at import time), makes the
`app` package importable, and registers the custom markers.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-please-ignore-0123456789abcd")
os.environ.setdefault("APP_PASSWORD", "test-password-123")
os.environ.pop("DB_ENCRYPTION_KEY", None)

_tmp_dir = tempfile.mkdtemp(prefix="dvbm_test_")
os.environ.setdefault("DB_PATH", os.path.join(_tmp_dir, "dvbm_test.db"))
# Settings reads these at import time. Without them the defaults (/data,
# /backups) are baked in, which do not exist outside the container — the
# integration tests then fail with a permission error on /backups depending on
# which test module imported the config first.
os.environ.setdefault("DATA_DIR", os.path.join(_tmp_dir, "data"))
os.environ.setdefault("BACKUP_TEMP_DIR", os.path.join(_tmp_dir, "backups"))
os.makedirs(os.environ["DATA_DIR"], exist_ok=True)
os.makedirs(os.environ["BACKUP_TEMP_DIR"], exist_ok=True)

# backend/ — so `import app.…` works no matter where pytest is invoked from.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires a running Docker daemon"
    )
    config.addinivalue_line(
        "markers", "slow: noticeably slower than the rest of the suite"
    )
