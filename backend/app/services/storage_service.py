"""Storage backend service.

Handles uploading / downloading / deleting backup archives to different
storage targets: local filesystem, S3, FTP/SFTP, and rclone remotes.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
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
        """Delete a remote object. Raises on failure so callers can react."""
        handler = self._get_handler(backend_type)
        return handler["delete"](config, remote_path)

    # ------------------------------------------------------------------
    # Remote size (upload verification)
    # ------------------------------------------------------------------

    def remote_size(self, backend_type: str, config: dict[str, Any], remote_path: str) -> int | None:
        """Return the size in bytes of a remote object, or None if unknown."""
        handler = self._get_handler(backend_type)
        if "size" not in handler:
            return None
        try:
            return handler["size"](config, remote_path)
        except Exception as exc:
            logger.warning("Could not stat remote object %s: %s", remote_path, exc)
            return None

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------

    def test_connection(self, backend_type: str, config: dict[str, Any]) -> tuple[bool, str]:
        handler = self._get_handler(backend_type)
        return handler["test"](config)

    # ------------------------------------------------------------------
    # List files
    # ------------------------------------------------------------------

    def list_files(
        self,
        backend_type: str,
        config: dict[str, Any],
        prefix: str = "",
        suffix: str = ".tar.gz",
    ) -> list[dict[str, Any]]:
        """List files on the storage backend. Returns list of {name, size, path}.

        suffix filters by file extension (default ".tar.gz"; pass ".zip" for config backups).
        """
        handler = self._get_handler(backend_type)
        if "list" not in handler:
            raise NotImplementedError(f"list_files not supported for {backend_type}")
        return handler["list"](config, prefix, suffix)

    # ------------------------------------------------------------------
    # Handler registry (built once as a class-level constant)
    # ------------------------------------------------------------------

    def _get_handler(self, backend_type: str) -> dict:
        if backend_type not in _HANDLERS:
            raise ValueError(f"Unsupported storage backend type: {backend_type}")
        return _HANDLERS[backend_type]

    # ==================================================================
    # Connection helpers
    # ==================================================================

    @staticmethod
    def _s3_client(config: dict):
        """Return a boto3 S3 client configured from the storage backend config."""
        import boto3
        return boto3.client(
            "s3",
            region_name=config.get("region", "us-east-1"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            endpoint_url=config.get("endpoint_url") or None,
        )

    # Host keys accepted on first use are recorded here so later connections
    # are pinned to the same server.
    KNOWN_HOSTS_PATH = "known_hosts"

    @staticmethod
    def _known_hosts_file() -> Path:
        from app.config import settings

        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return settings.DATA_DIR / StorageService.KNOWN_HOSTS_PATH

    @staticmethod
    def _verify_host_key(transport, host: str, port: int, expected_fingerprint: str = "") -> None:
        """Verify the server's host key against a pin or the known_hosts file.

        Raw paramiko Transport does no host key checking at all, which lets any
        machine on the path impersonate the backup server and collect the
        password plus every archive.
        """
        import base64
        import hashlib

        key = transport.get_remote_server_key()
        fingerprint = "SHA256:" + base64.b64encode(
            hashlib.sha256(key.asbytes()).digest()
        ).decode().rstrip("=")

        if expected_fingerprint:
            if fingerprint != expected_fingerprint.strip():
                raise RuntimeError(
                    f"SFTP host key mismatch for {host}:{port} — expected "
                    f"{expected_fingerprint.strip()}, got {fingerprint}"
                )
            return

        # Trust-on-first-use: remember the key and require it to match later.
        entry_host = f"[{host}]:{port}" if port != 22 else host
        store = StorageService._known_hosts_file()
        known: dict[str, str] = {}
        if store.is_file():
            for line in store.read_text().splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    known[parts[0]] = parts[1].strip()

        seen = known.get(entry_host)
        if seen is None:
            with store.open("a") as fh:
                fh.write(f"{entry_host} {fingerprint}\n")
            logger.warning("Pinned new SFTP host key for %s: %s", entry_host, fingerprint)
        elif seen != fingerprint:
            raise RuntimeError(
                f"SFTP host key for {entry_host} changed (was {seen}, now {fingerprint}). "
                "If this is expected, remove the entry from the known_hosts file in DATA_DIR."
            )

    @staticmethod
    @contextlib.contextmanager
    def _sftp_connect(config: dict):
        """Context manager that yields a connected paramiko SFTPClient."""
        import paramiko
        host = config["host"]
        port = int(config.get("port", 22))
        transport = paramiko.Transport((host, port))
        try:
            transport.start_client(timeout=30)
            StorageService._verify_host_key(
                transport, host, port, config.get("host_key_fingerprint", "")
            )
            transport.auth_password(
                username=config.get("username", ""),
                password=config.get("password", ""),
            )
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                yield sftp
            finally:
                sftp.close()
        finally:
            transport.close()

    @staticmethod
    @contextlib.contextmanager
    def _ftp_connect(config: dict):
        """Context manager that yields a connected FTP/FTP_TLS client."""
        from ftplib import FTP, FTP_TLS
        ftp_class = FTP_TLS if config.get("use_tls", False) else FTP
        ftp = ftp_class()
        ftp.connect(config["host"], config.get("port", 21))
        ftp.login(config.get("username", ""), config.get("password", ""))
        if config.get("use_tls"):
            ftp.prot_p()
        try:
            yield ftp
        finally:
            try:
                ftp.quit()
            except Exception:
                pass

    # ==================================================================
    # Local FS
    # ==================================================================

    # Local filesystem backends are confined to these roots so an operator
    # cannot point one at /etc.
    LOCALFS_ROOTS = ("/local-backups", "/backups")

    @staticmethod
    def _localfs_resolve(path: str) -> str:
        """Resolve *path* and verify it sits under an allowed root."""
        resolved = os.path.realpath(path)
        for root in StorageService.LOCALFS_ROOTS:
            root_real = os.path.realpath(root)
            if resolved == root_real or resolved.startswith(root_real + os.sep):
                return resolved
        raise ValueError(
            f"Local path '{path}' is outside the allowed roots "
            f"({', '.join(StorageService.LOCALFS_ROOTS)})"
        )

    @staticmethod
    def _localfs_size(config: dict, remote_path: str) -> int:
        return os.path.getsize(StorageService._localfs_resolve(remote_path))

    @staticmethod
    def _localfs_upload(config: dict, local_path: str, remote_name: str) -> str:
        dest_dir = StorageService._localfs_resolve(config.get("path", "/local-backups"))
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, remote_name)
        # Avoid error when source and destination resolve to the same file
        if os.path.abspath(local_path) == os.path.abspath(dest):
            logger.info("Local FS: file already at destination %s", dest)
            return dest
        shutil.move(local_path, dest)
        logger.info("Local FS: moved %s -> %s", local_path, dest)
        return dest

    @staticmethod
    def _localfs_download(config: dict, remote_path: str, local_path: str) -> str:
        if os.path.abspath(remote_path) == os.path.abspath(local_path):
            return local_path
        shutil.copy2(remote_path, local_path)
        return local_path

    @staticmethod
    def _localfs_delete(config: dict, remote_path: str) -> bool:
        # Raises on failure: silently returning False caused retention to drop
        # the DB row while leaving the file on disk forever.
        os.remove(StorageService._localfs_resolve(remote_path))
        return True


    @staticmethod
    def _localfs_test(config: dict) -> tuple[bool, str]:
        # Default must match _localfs_upload/_localfs_list so the connection
        # test validates the same directory backups are actually written to.
        path = config.get("path", "/local-backups")
        try:
            os.makedirs(path, exist_ok=True)
            test_file = os.path.join(path, ".dvbm-test")
            Path(test_file).touch()
            os.remove(test_file)
            return True, f"Local path '{path}' is writable"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _localfs_list(config: dict, prefix: str = "", suffix: str = ".tar.gz") -> list[dict]:
        base = config.get("path", "/local-backups")
        results = []
        if not os.path.isdir(base):
            return results
        for name in os.listdir(base):
            full = os.path.join(base, name)
            if not os.path.isfile(full):
                continue
            if prefix and not name.startswith(prefix):
                continue
            if not name.endswith(suffix):
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            results.append({"name": name, "size": size, "path": full})
        return results

    # ==================================================================
    # S3
    # ==================================================================

    @staticmethod
    def _s3_upload(config: dict, local_path: str, remote_name: str) -> str:
        client = StorageService._s3_client(config)
        bucket = config["bucket"]
        key = f"{config.get('prefix', '').strip('/')}/{remote_name}".lstrip("/")
        client.upload_file(local_path, bucket, key)
        logger.info("S3: uploaded %s -> s3://%s/%s", local_path, bucket, key)
        return f"s3://{bucket}/{key}"

    @staticmethod
    def _s3_download(config: dict, remote_path: str, local_path: str) -> str:
        client = StorageService._s3_client(config)
        bucket = config["bucket"]
        key = remote_path.replace(f"s3://{bucket}/", "")
        client.download_file(bucket, key, local_path)
        return local_path

    @staticmethod
    def _s3_delete(config: dict, remote_path: str) -> bool:
        # Raises on failure so retention keeps the DB row and can retry,
        # rather than orphaning the object in the bucket.
        client = StorageService._s3_client(config)
        bucket = config["bucket"]
        key = remote_path.replace(f"s3://{bucket}/", "")
        client.delete_object(Bucket=bucket, Key=key)
        return True

    @staticmethod
    def _s3_size(config: dict, remote_path: str) -> int:
        client = StorageService._s3_client(config)
        bucket = config["bucket"]
        key = remote_path.replace(f"s3://{bucket}/", "")
        return int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])


    @staticmethod
    def _s3_test(config: dict) -> tuple[bool, str]:
        try:
            client = StorageService._s3_client(config)
            bucket = config.get("bucket", "")
            client.head_bucket(Bucket=bucket)
            return True, f"S3 bucket '{bucket}' is accessible"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _s3_list(config: dict, prefix: str = "", suffix: str = ".tar.gz") -> list[dict]:
        client = StorageService._s3_client(config)
        bucket = config["bucket"]
        s3_prefix = config.get("prefix", "").strip("/")
        if prefix:
            s3_prefix = f"{s3_prefix}/{prefix}" if s3_prefix else prefix
        results = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                name = key.rsplit("/", 1)[-1]
                if not name.endswith(suffix):
                    continue
                results.append({
                    "name": name,
                    "size": obj.get("Size", 0),
                    "path": f"s3://{bucket}/{key}",
                })
        return results

    # ==================================================================
    # FTP / SFTP
    # ==================================================================

    @staticmethod
    def _ftp_upload(config: dict, local_path: str, remote_name: str) -> str:
        use_sftp = config.get("use_sftp", False)
        remote_dir = config.get("path", "/backups")
        remote_full = f"{remote_dir}/{remote_name}"

        if use_sftp:
            with StorageService._sftp_connect(config) as sftp:
                try:
                    sftp.stat(remote_dir)
                except FileNotFoundError:
                    sftp.mkdir(remote_dir)
                sftp.put(local_path, remote_full)
        else:
            with StorageService._ftp_connect(config) as ftp:
                try:
                    ftp.cwd(remote_dir)
                except Exception:
                    ftp.mkd(remote_dir)
                    ftp.cwd(remote_dir)
                with open(local_path, "rb") as f:
                    ftp.storbinary(f"STOR {remote_name}", f)

        logger.info("FTP: uploaded %s -> %s", local_path, remote_full)
        return remote_full

    @staticmethod
    def _ftp_download(config: dict, remote_path: str, local_path: str) -> str:
        use_sftp = config.get("use_sftp", False)

        if use_sftp:
            with StorageService._sftp_connect(config) as sftp:
                sftp.get(remote_path, local_path)
        else:
            with StorageService._ftp_connect(config) as ftp:
                with open(local_path, "wb") as f:
                    ftp.retrbinary(f"RETR {remote_path}", f.write)

        return local_path

    @staticmethod
    def _ftp_delete(config: dict, remote_path: str) -> bool:
        # Raises on failure — see _s3_delete.
        use_sftp = config.get("use_sftp", False)
        if use_sftp:
            with StorageService._sftp_connect(config) as sftp:
                sftp.remove(remote_path)
        else:
            with StorageService._ftp_connect(config) as ftp:
                ftp.delete(remote_path)
        return True

    @staticmethod
    def _ftp_size(config: dict, remote_path: str) -> int:
        if config.get("use_sftp", False):
            with StorageService._sftp_connect(config) as sftp:
                return int(sftp.stat(remote_path).st_size)
        with StorageService._ftp_connect(config) as ftp:
            size = ftp.size(remote_path)
            if size is None:
                raise RuntimeError("FTP server did not report a size")
            return int(size)


    @staticmethod
    def _ftp_test(config: dict) -> tuple[bool, str]:
        try:
            use_sftp = config.get("use_sftp", False)
            if use_sftp:
                with StorageService._sftp_connect(config) as sftp:
                    sftp.listdir(".")
                return True, f"SFTP connection to {config['host']} successful"
            else:
                with StorageService._ftp_connect(config) as ftp:
                    ftp.nlst()
                return True, f"FTP connection to {config['host']} successful"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _ftp_list(config: dict, prefix: str = "", suffix: str = ".tar.gz") -> list[dict]:
        use_sftp = config.get("use_sftp", False)
        remote_dir = config.get("path", "/backups")
        results = []

        if use_sftp:
            with StorageService._sftp_connect(config) as sftp:
                for attr in sftp.listdir_attr(remote_dir):
                    if not attr.filename.endswith(suffix):
                        continue
                    if prefix and not attr.filename.startswith(prefix):
                        continue
                    results.append({
                        "name": attr.filename,
                        "size": attr.st_size or 0,
                        "path": f"{remote_dir}/{attr.filename}",
                    })
        else:
            with StorageService._ftp_connect(config) as ftp:
                entries = []
                ftp.retrlines(f"LIST {remote_dir}", entries.append)
                for entry in entries:
                    parts = entry.split(None, 8)
                    if len(parts) < 9:
                        continue
                    name = parts[8]
                    if not name.endswith(suffix):
                        continue
                    if prefix and not name.startswith(prefix):
                        continue
                    try:
                        size = int(parts[4])
                    except (ValueError, IndexError):
                        size = 0
                    results.append({
                        "name": name,
                        "size": size,
                        "path": f"{remote_dir}/{name}",
                    })

        return results

    # ==================================================================
    # Rclone
    # ==================================================================

    # The extra-flags field is free text in the UI and goes straight into
    # rclone's argv. An allowlist is used rather than a denylist: blocking only
    # --config still permits --log-file (writes attacker-controlled content to
    # any path the process can reach) and --dump, among others.
    _ALLOWED_RCLONE_FLAG = re.compile(
        r"^--(transfers|checkers|bwlimit|retries|low-level-retries|timeout|"
        r"contimeout|multi-thread-streams|multi-thread-cutoff|s3-chunk-size|"
        r"drive-chunk-size|buffer-size|tpslimit|order-by|fast-list|"
        r"ignore-checksum|no-check-certificate|size-only|checksum|update)"
        r"(=[A-Za-z0-9._:+-]+)?$"
    )

    @staticmethod
    def _rclone_extra_flags(config: dict) -> list[str]:
        """Parse the storage's extra rclone flags safely.

        Uses shlex so quoted arguments are handled correctly, then validates
        each token against an allowlist of transfer-tuning flags.
        """
        import shlex

        raw = config.get("flags", "") or ""
        if not raw.strip():
            return []
        try:
            tokens = shlex.split(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid rclone flags: {exc}")
        # Values may be attached (--bwlimit=1M) or separate (--bwlimit 1M), so
        # a bare token following an allowed flag is treated as its value.
        expect_value = False
        for tok in tokens:
            if expect_value and not tok.startswith("-"):
                expect_value = False
                continue
            match = StorageService._ALLOWED_RCLONE_FLAG.match(tok)
            if not match:
                raise ValueError(
                    f"rclone flag '{tok}' is not permitted. Allowed flags are "
                    "limited to transfer tuning options such as --transfers=4 "
                    "or --bwlimit=10M."
                )
            # No "=value" attached, so the next token may be this flag's value.
            expect_value = "=" not in tok
        return tokens

    @staticmethod
    def _rclone_upload(config: dict, local_path: str, remote_name: str) -> str:
        from app.config import settings

        remote = config.get("remote_name", "")
        remote_dir = config.get("path", "").rstrip("/")
        dest = f"{remote}:{remote_dir}/{remote_name}"
        cmd = [settings.RCLONE_BINARY, "copyto", local_path, dest, "--config", settings.RCLONE_CONFIG]
        cmd.extend(StorageService._rclone_extra_flags(config))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"rclone upload failed: {result.stderr}")
        logger.info("Rclone: uploaded %s -> %s", local_path, dest)
        return dest

    @staticmethod
    def _rclone_download(config: dict, remote_path: str, local_path: str) -> str:
        from app.config import settings

        cmd = [settings.RCLONE_BINARY, "copyto", remote_path, local_path, "--config", settings.RCLONE_CONFIG]
        cmd.extend(StorageService._rclone_extra_flags(config))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"rclone download failed: {result.stderr}")
        # Verify the file was actually downloaded
        if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            raise RuntimeError(f"rclone download produced empty or missing file: {local_path}")
        return local_path

    @staticmethod
    def _rclone_delete(config: dict, remote_path: str) -> bool:
        from app.config import settings

        # Raises on failure — see _s3_delete.
        cmd = [settings.RCLONE_BINARY, "deletefile", remote_path, "--config", settings.RCLONE_CONFIG]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"rclone delete failed: {result.stderr.strip()}")
        return True

    @staticmethod
    def _rclone_size(config: dict, remote_path: str) -> int:
        from app.config import settings

        cmd = [settings.RCLONE_BINARY, "lsjson", remote_path, "--config", settings.RCLONE_CONFIG]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"rclone lsjson failed: {result.stderr.strip()}")
        entries = json.loads(result.stdout or "[]")
        if not entries:
            raise RuntimeError(f"rclone reported no object at {remote_path}")
        return int(entries[0]["Size"])


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

    @staticmethod
    def _rclone_list(config: dict, prefix: str = "", suffix: str = ".tar.gz") -> list[dict]:
        import json as _json

        from app.config import settings

        remote = config.get("remote_name", "")
        remote_dir = config.get("path", "").rstrip("/")
        target = f"{remote}:{remote_dir}" if remote_dir else f"{remote}:"
        cmd = [
            settings.RCLONE_BINARY, "lsjson", target,
            "--config", settings.RCLONE_CONFIG,
            "--no-modtime",
        ]
        cmd.extend(StorageService._rclone_extra_flags(config))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"rclone lsjson failed: {result.stderr}")

        items = _json.loads(result.stdout)
        results = []
        for item in items:
            if item.get("IsDir"):
                continue
            name = item.get("Name", "")
            if not name.endswith(suffix):
                continue
            if prefix and not name.startswith(prefix):
                continue
            path_part = f"{remote_dir}/{name}" if remote_dir else name
            results.append({
                "name": name,
                "size": item.get("Size", 0),
                "path": f"{remote}:{path_part}",
            })
        return results


# Handler registry — built once at module load time (all methods are static).
_HANDLERS: dict[str, dict] = {
    "localfs": {
        "upload": StorageService._localfs_upload,
        "download": StorageService._localfs_download,
        "delete": StorageService._localfs_delete,
        "size": StorageService._localfs_size,
        "test": StorageService._localfs_test,
        "list": StorageService._localfs_list,
    },
    "s3": {
        "upload": StorageService._s3_upload,
        "download": StorageService._s3_download,
        "delete": StorageService._s3_delete,
        "size": StorageService._s3_size,
        "test": StorageService._s3_test,
        "list": StorageService._s3_list,
    },
    "ftp": {
        "upload": StorageService._ftp_upload,
        "download": StorageService._ftp_download,
        "delete": StorageService._ftp_delete,
        "size": StorageService._ftp_size,
        "test": StorageService._ftp_test,
        "list": StorageService._ftp_list,
    },
    "rclone": {
        "upload": StorageService._rclone_upload,
        "download": StorageService._rclone_download,
        "delete": StorageService._rclone_delete,
        "size": StorageService._rclone_size,
        "test": StorageService._rclone_test,
        "list": StorageService._rclone_list,
    },
}

storage_service = StorageService()
