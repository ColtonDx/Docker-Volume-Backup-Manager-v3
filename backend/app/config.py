import os
from pathlib import Path


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
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production-please")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    # Database
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))
    DB_PATH: str = os.getenv("DB_PATH", "")

    # Database at-rest encryption (SQLCipher / AES-256).
    # When set, the SQLite database is encrypted on disk.
    # WARNING: losing this key makes the database permanently unreadable.
    DB_ENCRYPTION_KEY: str = os.getenv("DB_ENCRYPTION_KEY", "")

    # Docker
    DOCKER_SOCKET: str = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")
    DOCKER_LABEL_KEY: str = os.getenv("DOCKER_LABEL_KEY", "dvbm.job")

    # Backup
    BACKUP_TEMP_DIR: Path = Path(os.getenv("BACKUP_TEMP_DIR", "/tmp/dvbm"))
    DEFAULT_COMPRESSION: str = os.getenv("DEFAULT_COMPRESSION", "gzip")

    # Rclone
    RCLONE_ENABLED: bool = os.getenv("RCLONE_ENABLED", "false").lower() == "true"
    RCLONE_BINARY: str = os.getenv("RCLONE_BINARY", "/usr/bin/rclone")
    RCLONE_CONFIG: str = os.getenv("RCLONE_CONFIG", "/root/.config/rclone/rclone.conf")

    # Timezone
    TIMEZONE: str = os.getenv("TZ", "UTC")

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
