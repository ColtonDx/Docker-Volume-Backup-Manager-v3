"""Storage backend service.

Handles uploading / downloading / deleting backup archives to different
storage targets: local filesystem, S3, FTP/SFTP, and rclone remotes.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StorageService:
    """Unified interface for backup storage backends."""

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload(self, backend_type: str, config: dict[str, Any], local_path: str, remote_name: str) -> str:
        """Upload a file to the configured storage. Returns the remote path/key."""
        handler = self._get_handler(backend_type)
        return handler["upload"](config, local_path, remote_name)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(self, backend_type: str, config: dict[str, Any], remote_path: str, local_path: str) -> str:
        """Download a file from storage. Returns the local path."""
        handler = self._get_handler(backend_type)
        return handler["download"](config, remote_path, local_path)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_remote(self, backend_type: str, config: dict[str, Any], remote_path: str) -> bool:
        handler = self._get_handler(backend_type)
        return handler["delete"](config, remote_path)

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------

    def test_connection(self, backend_type: str, config: dict[str, Any]) -> tuple[bool, str]:
        handler = self._get_handler(backend_type)
        return handler["test"](config)

    # ------------------------------------------------------------------
    # Handler registry
    # ------------------------------------------------------------------

    def _get_handler(self, backend_type: str) -> dict:
        handlers = {
            "localfs": {
                "upload": self._localfs_upload,
                "download": self._localfs_download,
                "delete": self._localfs_delete,
                "test": self._localfs_test,
            },
            "s3": {
                "upload": self._s3_upload,
                "download": self._s3_download,
                "delete": self._s3_delete,
                "test": self._s3_test,
            },
            "ftp": {
                "upload": self._ftp_upload,
                "download": self._ftp_download,
                "delete": self._ftp_delete,
                "test": self._ftp_test,
            },
            "rclone": {
                "upload": self._rclone_upload,
                "download": self._rclone_download,
                "delete": self._rclone_delete,
                "test": self._rclone_test,
            },
        }
        if backend_type not in handlers:
            raise ValueError(f"Unsupported storage backend type: {backend_type}")
        return handlers[backend_type]

    # ==================================================================
    # Local FS
    # ==================================================================

    @staticmethod
    def _localfs_upload(config: dict, local_path: str, remote_name: str) -> str:
        dest_dir = config.get("path", "/backups")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, remote_name)
        shutil.copy2(local_path, dest)
        logger.info("Local FS: copied %s -> %s", local_path, dest)
        return dest

    @staticmethod
    def _localfs_download(config: dict, remote_path: str, local_path: str) -> str:
        shutil.copy2(remote_path, local_path)
        return local_path

    @staticmethod
    def _localfs_delete(config: dict, remote_path: str) -> bool:
        try:
            os.remove(remote_path)
            return True
        except OSError:
            return False

    @staticmethod
    def _localfs_test(config: dict) -> tuple[bool, str]:
        path = config.get("path", "/backups")
        try:
            os.makedirs(path, exist_ok=True)
            test_file = os.path.join(path, ".backup-buddy-test")
            Path(test_file).touch()
            os.remove(test_file)
            return True, f"Local path '{path}' is writable"
        except Exception as exc:
            return False, str(exc)

    # ==================================================================
    # S3
    # ==================================================================

    @staticmethod
    def _s3_upload(config: dict, local_path: str, remote_name: str) -> str:
        import boto3

        client = boto3.client(
            "s3",
            region_name=config.get("region", "us-east-1"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            endpoint_url=config.get("endpoint_url") or None,
        )
        bucket = config["bucket"]
        key = f"{config.get('prefix', '').strip('/')}/{remote_name}".lstrip("/")
        client.upload_file(local_path, bucket, key)
        logger.info("S3: uploaded %s -> s3://%s/%s", local_path, bucket, key)
        return f"s3://{bucket}/{key}"

    @staticmethod
    def _s3_download(config: dict, remote_path: str, local_path: str) -> str:
        import boto3

        client = boto3.client(
            "s3",
            region_name=config.get("region", "us-east-1"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            endpoint_url=config.get("endpoint_url") or None,
        )
        bucket = config["bucket"]
        # remote_path is "s3://bucket/key" or just "key"
        key = remote_path.replace(f"s3://{bucket}/", "")
        client.download_file(bucket, key, local_path)
        return local_path

    @staticmethod
    def _s3_delete(config: dict, remote_path: str) -> bool:
        import boto3

        try:
            client = boto3.client(
                "s3",
                region_name=config.get("region", "us-east-1"),
                aws_access_key_id=config.get("access_key_id"),
                aws_secret_access_key=config.get("secret_access_key"),
                endpoint_url=config.get("endpoint_url") or None,
            )
            bucket = config["bucket"]
            key = remote_path.replace(f"s3://{bucket}/", "")
            client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False

    @staticmethod
    def _s3_test(config: dict) -> tuple[bool, str]:
        try:
            import boto3

            client = boto3.client(
                "s3",
                region_name=config.get("region", "us-east-1"),
                aws_access_key_id=config.get("access_key_id"),
                aws_secret_access_key=config.get("secret_access_key"),
                endpoint_url=config.get("endpoint_url") or None,
            )
            bucket = config.get("bucket", "")
            client.head_bucket(Bucket=bucket)
            return True, f"S3 bucket '{bucket}' is accessible"
        except Exception as exc:
            return False, str(exc)

    # ==================================================================
    # FTP / SFTP
    # ==================================================================

    @staticmethod
    def _ftp_upload(config: dict, local_path: str, remote_name: str) -> str:
        use_sftp = config.get("use_sftp", False)
        remote_dir = config.get("path", "/backups")
        remote_full = f"{remote_dir}/{remote_name}"

        if use_sftp:
            import paramiko

            transport = paramiko.Transport((config["host"], config.get("port", 22)))
            transport.connect(username=config.get("username", ""), password=config.get("password", ""))
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                sftp.mkdir(remote_dir)
            sftp.put(local_path, remote_full)
            sftp.close()
            transport.close()
        else:
            from ftplib import FTP, FTP_TLS

            ftp_class = FTP_TLS if config.get("use_tls", False) else FTP
            ftp = ftp_class()
            ftp.connect(config["host"], config.get("port", 21))
            ftp.login(config.get("username", ""), config.get("password", ""))
            if config.get("use_tls"):
                ftp.prot_p()
            try:
                ftp.cwd(remote_dir)
            except Exception:
                ftp.mkd(remote_dir)
                ftp.cwd(remote_dir)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)
            ftp.quit()

        logger.info("FTP: uploaded %s -> %s", local_path, remote_full)
        return remote_full

    @staticmethod
    def _ftp_download(config: dict, remote_path: str, local_path: str) -> str:
        use_sftp = config.get("use_sftp", False)

        if use_sftp:
            import paramiko

            transport = paramiko.Transport((config["host"], config.get("port", 22)))
            transport.connect(username=config.get("username", ""), password=config.get("password", ""))
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.get(remote_path, local_path)
            sftp.close()
            transport.close()
        else:
            from ftplib import FTP, FTP_TLS

            ftp_class = FTP_TLS if config.get("use_tls", False) else FTP
            ftp = ftp_class()
            ftp.connect(config["host"], config.get("port", 21))
            ftp.login(config.get("username", ""), config.get("password", ""))
            if config.get("use_tls"):
                ftp.prot_p()
            with open(local_path, "wb") as f:
                ftp.retrbinary(f"RETR {remote_path}", f.write)
            ftp.quit()

        return local_path

    @staticmethod
    def _ftp_delete(config: dict, remote_path: str) -> bool:
        try:
            use_sftp = config.get("use_sftp", False)
            if use_sftp:
                import paramiko

                transport = paramiko.Transport((config["host"], config.get("port", 22)))
                transport.connect(username=config.get("username", ""), password=config.get("password", ""))
                sftp = paramiko.SFTPClient.from_transport(transport)
                sftp.remove(remote_path)
                sftp.close()
                transport.close()
            else:
                from ftplib import FTP, FTP_TLS

                ftp_class = FTP_TLS if config.get("use_tls", False) else FTP
                ftp = ftp_class()
                ftp.connect(config["host"], config.get("port", 21))
                ftp.login(config.get("username", ""), config.get("password", ""))
                ftp.delete(remote_path)
                ftp.quit()
            return True
        except Exception:
            return False

    @staticmethod
    def _ftp_test(config: dict) -> tuple[bool, str]:
        try:
            use_sftp = config.get("use_sftp", False)
            if use_sftp:
                import paramiko

                transport = paramiko.Transport((config["host"], config.get("port", 22)))
                transport.connect(username=config.get("username", ""), password=config.get("password", ""))
                sftp = paramiko.SFTPClient.from_transport(transport)
                sftp.listdir(".")
                sftp.close()
                transport.close()
                return True, f"SFTP connection to {config['host']} successful"
            else:
                from ftplib import FTP, FTP_TLS

                ftp_class = FTP_TLS if config.get("use_tls", False) else FTP
                ftp = ftp_class()
                ftp.connect(config["host"], config.get("port", 21))
                ftp.login(config.get("username", ""), config.get("password", ""))
                ftp.nlst()
                ftp.quit()
                return True, f"FTP connection to {config['host']} successful"
        except Exception as exc:
            return False, str(exc)

    # ==================================================================
    # Rclone
    # ==================================================================

    @staticmethod
    def _rclone_upload(config: dict, local_path: str, remote_name: str) -> str:
        from app.config import settings

        remote = config.get("remote_name", "")
        remote_dir = config.get("path", "").rstrip("/")
        dest = f"{remote}:{remote_dir}/{remote_name}"
        cmd = [settings.RCLONE_BINARY, "copyto", local_path, dest, "--config", settings.RCLONE_CONFIG]
        extra_flags = config.get("flags", "")
        if extra_flags:
            cmd.extend(extra_flags.split())
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"rclone upload failed: {result.stderr}")
        logger.info("Rclone: uploaded %s -> %s", local_path, dest)
        return dest

    @staticmethod
    def _rclone_download(config: dict, remote_path: str, local_path: str) -> str:
        from app.config import settings

        cmd = [settings.RCLONE_BINARY, "copyto", remote_path, local_path, "--config", settings.RCLONE_CONFIG]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"rclone download failed: {result.stderr}")
        return local_path

    @staticmethod
    def _rclone_delete(config: dict, remote_path: str) -> bool:
        from app.config import settings

        try:
            cmd = [settings.RCLONE_BINARY, "deletefile", remote_path, "--config", settings.RCLONE_CONFIG]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _rclone_test(config: dict) -> tuple[bool, str]:
        from app.config import settings

        try:
            remote = config.get("remote_name", "")
            cmd = [settings.RCLONE_BINARY, "lsd", f"{remote}:", "--config", settings.RCLONE_CONFIG]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True, f"Rclone remote '{remote}' is accessible"
            return False, result.stderr.strip()
        except Exception as exc:
            return False, str(exc)


storage_service = StorageService()
