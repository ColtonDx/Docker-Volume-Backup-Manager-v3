"""Test configuration.

Sets deterministic environment variables before any application module is
imported (config, auth, database all read these at import time).
"""

import os
import tempfile

os.environ.setdefault("JWT_SECRET", "test-secret-key-please-ignore-0123456789abcd")
os.environ.setdefault("APP_PASSWORD", "test-password-123")
os.environ.pop("DB_ENCRYPTION_KEY", None)

_tmp_dir = tempfile.mkdtemp(prefix="dvbm_test_")
os.environ.setdefault("DB_PATH", os.path.join(_tmp_dir, "dvbm_test.db"))
