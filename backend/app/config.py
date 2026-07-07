import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# Signing keys that must never be used: the empty string (unset) and the old
# built-in placeholder that shipped in previous versions.
_INSECURE_JWT_SECRETS = {"", "change-me-in-production-please"}

# Passwords weak enough to warrant a loud startup warning.
_WEAK_PASSWORDS = {"", "admin", "changeme", "password"}


def _read_version() -> str:
    """Read version from the VERSION file at the repo/container root."""
    for candidate in (
        Path(__file__).resolve().parent.parent.parent / "VERSION",  # dev: repo root
        Path(__file__).resolve().parent.parent / "VERSION",        # container: /app/VERSION
    ):
        if candidate.is_file():
            return candidate.read_text().strip()
    return "0.0.0-dev"


class Settings:
    """Application settings loaded from environment variables."""

    APP_NAME: str = os.getenv("APP_NAME", "Docker Volume Backup Manager")
    APP_VERSION: str = _read_version()

    # Auth
    AUTH_PASSWORD: str = os.getenv("APP_PASSWORD", "admin")
    # No built-in default: a hardcoded signing key is public and lets anyone
    # forge admin tokens. Enforced non-empty at startup by validate_secrets().
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    # Database
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))
    DB_PATH: str = os.getenv("DB_PATH", "")

    # Database at-rest encryption (SQLCipher / AES-256).
    # When set, the SQLite database is encrypted on disk.
    # WARNING: losing this key makes the database permanently unreadable.
    DB_ENCRYPTION_KEY: str = os.getenv("DB_ENCRYPTION_KEY", "")

    # Opt-in migration of databases encrypted with the legacy (unsalted
    # single-SHA-256 raw key) scheme to the stronger native SQLCipher KDF.
    # Left false, the app refuses to start on a legacy-encrypted DB so the
    # operator can back up / roll back first. Set true to allow the one-time
    # in-place re-encryption (a verified .prekdf.bak backup is kept).
    MIGRATE_ENCRYPTED_DB: bool = os.getenv("MIGRATE_ENCRYPTED_DB", "false").lower() == "true"

    # Docker
    DOCKER_SOCKET: str = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")
    DOCKER_LABEL_KEY: str = os.getenv("DOCKER_LABEL_KEY", "dvbm.job")

    # Backup
    BACKUP_TEMP_DIR: Path = Path(os.getenv("BACKUP_TEMP_DIR", "/backups"))
    DEFAULT_COMPRESSION: str = os.getenv("DEFAULT_COMPRESSION", "gzip")

    # Rclone
    RCLONE_ENABLED: bool = os.getenv("RCLONE_ENABLED", "false").lower() == "true"
    RCLONE_BINARY: str = os.getenv("RCLONE_BINARY", "/usr/bin/rclone")
    RCLONE_CONFIG: str = os.getenv("RCLONE_CONFIG", "/root/.config/rclone/rclone.conf")

    # Timezone
    TIMEZONE: str = os.getenv("TZ", "UTC")

    # Maximum number of backup jobs that may run at the same time.
    # 1 (default) means jobs run sequentially — safest when jobs share containers.
    # Increase only if all jobs target completely separate containers.
    MAX_CONCURRENT_BACKUPS: int = int(os.getenv("MAX_CONCURRENT_BACKUPS", "1"))

    # Maximum time a single backup or restore job may run before it is forcibly
    # marked as failed and the semaphore slot is released. Default: 2 hours.
    # Set to 0 to disable the timeout (not recommended).
    JOB_TIMEOUT_SECONDS: int = int(os.getenv("JOB_TIMEOUT_SECONDS", "7200"))

    # Allowed hosts – comma-separated Host header values to accept.
    # Use "*" (default) to allow all. Restrict in production, e.g.:
    #   ALLOWED_HOSTS=myhost.example.com,localhost
    ALLOWED_HOSTS: str = os.getenv("ALLOWED_HOSTS", "*")

    # Allowed CORS origins – comma-separated.
    # Use "*" (default) to allow all. Restrict in production, e.g.:
    #   ALLOWED_ORIGINS=https://myhost.example.com
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")

    # HTTPS / TLS
    # SSL_ENABLED=true (default): a self-signed cert is auto-generated on
    # first start and stored in SSL_CERT_DIR. Set SSL_ENABLED=false for plain HTTP.
    SSL_ENABLED: bool = os.getenv("SSL_ENABLED", "true").lower() == "true"
    SSL_CERT_DIR: Path = Path(os.getenv("SSL_CERT_DIR", "/data/certs"))
    # Override these to supply your own cert (e.g. from Let's Encrypt).
    _SSL_CERT_FILE: str = os.getenv("SSL_CERT_FILE", "")
    _SSL_KEY_FILE: str = os.getenv("SSL_KEY_FILE", "")

    # Guard so the password warning is emitted at most once per process.
    _secrets_validated: bool = False

    def validate_secrets(self) -> None:
        """Validate secret configuration at startup.

        - JWT_SECRET: hard failure if unset or left at the old built-in default.
          A public signing key allows anyone to forge admin tokens.
        - APP_PASSWORD: loud warning (non-fatal) if unset or a known-weak value.
        """
        if self.JWT_SECRET.strip() in _INSECURE_JWT_SECRETS:
            raise RuntimeError(
                "JWT_SECRET is not set (or still uses the old built-in default). "
                "A hardcoded signing key is public and lets anyone forge admin "
                "tokens. Set the JWT_SECRET environment variable to a strong "
                "random value before starting, for example:\n"
                "    JWT_SECRET=$(openssl rand -hex 32)\n"
                "Refusing to start with an insecure signing key."
            )

        if self._secrets_validated:
            return
        self._secrets_validated = True

        if self.AUTH_PASSWORD.strip().lower() in _WEAK_PASSWORDS:
            log.warning(
                "=" * 72 + "\n"
                "SECURITY WARNING: APP_PASSWORD is unset or set to a well-known "
                "default (%r). The web UI is effectively unprotected. Set "
                "APP_PASSWORD to a strong, unique value.\n" + "=" * 72,
                self.AUTH_PASSWORD,
            )

    @property
    def database_url(self) -> str:
        if self.DB_PATH:
            return f"sqlite:///{self.DB_PATH}"
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.DATA_DIR / 'dvbm.db'}"

    @property
    def db_file_path(self) -> Path:
        """Absolute Path to the SQLite database file."""
        url = self.database_url
        return Path(url[len("sqlite:///"):]).resolve()

    @property
    def allowed_hosts_list(self) -> list[str]:
        raw = self.ALLOWED_HOSTS.strip()
        if not raw or raw == "*":
            return ["*"]
        return [h.strip() for h in raw.split(",") if h.strip()]

    @property
    def allowed_origins_list(self) -> list[str]:
        raw = self.ALLOWED_ORIGINS.strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def ssl_cert_path(self) -> Path:
        if self._SSL_CERT_FILE:
            return Path(self._SSL_CERT_FILE)
        return self.SSL_CERT_DIR / "cert.pem"

    @property
    def ssl_key_path(self) -> Path:
        if self._SSL_KEY_FILE:
            return Path(self._SSL_KEY_FILE)
        return self.SSL_CERT_DIR / "key.pem"


settings = Settings()
