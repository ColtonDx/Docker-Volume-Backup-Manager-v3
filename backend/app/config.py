import os
from pathlib import Path


class Settings:
    """Application settings loaded from environment variables."""

    APP_NAME: str = os.getenv("APP_NAME", "Backup Buddy")
    APP_VERSION: str = "1.0.0"

    # Auth
    AUTH_PASSWORD: str = os.getenv("BACKUP_BUDDY_PASSWORD", "admin")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production-please")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    # Database
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))
    DB_PATH: str = os.getenv("DB_PATH", "")

    # Docker
    DOCKER_SOCKET: str = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")
    DOCKER_LABEL_KEY: str = os.getenv("DOCKER_LABEL_KEY", "backup-buddy.job")

    # Backup
    BACKUP_TEMP_DIR: Path = Path(os.getenv("BACKUP_TEMP_DIR", "/tmp/backup-buddy"))
    DEFAULT_COMPRESSION: str = os.getenv("DEFAULT_COMPRESSION", "gzip")

    # Rclone
    RCLONE_ENABLED: bool = os.getenv("RCLONE_ENABLED", "false").lower() == "true"
    RCLONE_BINARY: str = os.getenv("RCLONE_BINARY", "/usr/bin/rclone")
    RCLONE_CONFIG: str = os.getenv("RCLONE_CONFIG", "/root/.config/rclone/rclone.conf")

    # Timezone
    TIMEZONE: str = os.getenv("TZ", "UTC")

    @property
    def database_url(self) -> str:
        if self.DB_PATH:
            return f"sqlite:///{self.DB_PATH}"
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.DATA_DIR / 'backup_buddy.db'}"


settings = Settings()
