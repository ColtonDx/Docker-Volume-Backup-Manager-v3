"""Disposable Docker environment for the integration tests.

Everything created here is named with a per-run prefix and removed in teardown,
including when a test fails. Nothing touches the user's own containers, volumes
or images beyond pulling the small public images the tests need.
"""

from __future__ import annotations

import io
import socket
import subprocess
import tarfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import docker

# Every object this suite creates starts with this, so stray resources from a
# hard-killed run are trivially identifiable and removable.
PREFIX = "dvbmtest"

WORKLOAD_IMAGE = "busybox:1.36"
MINIO_IMAGE = "minio/minio:latest"
SFTP_IMAGE = "atmoz/sftp:alpine"

MINIO_USER = "dvbmtestaccess"
MINIO_PASSWORD = "dvbmtestsecret"
MINIO_BUCKET = "backups"

SFTP_USER = "dvbmtest"
SFTP_PASSWORD = "dvbmtestpw"


def free_port() -> int:
    """Ask the OS for an unused port.

    Racy in principle, but the window is small and it avoids hardcoding ports
    that may already be taken on a developer machine.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for(check, timeout: float, interval: float = 0.5, what: str = "condition"):
    """Poll *check* until it returns a truthy value or *timeout* elapses.

    Returns the truthy value. Raises TimeoutError with the last exception's
    message, which is far more useful than a bare timeout when a service
    fails to come up.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except Exception as exc:
            last_error = exc
        time.sleep(interval)
    detail = f" (last error: {last_error})" if last_error else ""
    raise TimeoutError(f"Timed out after {timeout}s waiting for {what}{detail}")


@dataclass
class TestEnv:
    """Owns every Docker object and temp path a test run creates."""

    client: docker.DockerClient
    run_id: str
    tmp_path: Path
    _containers: list = field(default_factory=list)
    _volumes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------

    def name(self, suffix: str) -> str:
        return f"{PREFIX}-{self.run_id}-{suffix}"

    # ------------------------------------------------------------------
    # Volumes
    # ------------------------------------------------------------------

    def create_volume(self, suffix: str, contents: dict[str, str] | None = None) -> str:
        """Create a named volume, optionally seeding it with files.

        *contents* maps relative path -> file body. Paths may include
        subdirectories, which are created as needed.
        """
        vol_name = self.name(suffix)
        self.client.volumes.create(name=vol_name)
        self._volumes.append(vol_name)
        if contents:
            self.write_volume(vol_name, contents)
        return vol_name

    def write_volume(self, volume: str, contents: dict[str, str]) -> None:
        """Write files into a volume via a short-lived helper container."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for rel_path, body in contents.items():
                data = body.encode()
                info = tarfile.TarInfo(name=rel_path)
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
        buf.seek(0)

        helper = self.client.containers.create(
            WORKLOAD_IMAGE,
            command="true",
            volumes={volume: {"bind": "/data", "mode": "rw"}},
            name=self.name(f"seed-{uuid.uuid4().hex[:8]}"),
        )
        try:
            helper.put_archive("/data", buf.getvalue())
        finally:
            helper.remove(force=True)

    def read_volume(self, volume: str) -> dict[str, str]:
        """Return {relative path: contents} for every regular file in a volume."""
        helper = self.client.containers.create(
            WORKLOAD_IMAGE,
            command="true",
            volumes={volume: {"bind": "/data", "mode": "ro"}},
            name=self.name(f"read-{uuid.uuid4().hex[:8]}"),
        )
        try:
            bits, _ = helper.get_archive("/data/.")
            raw = b"".join(bits)
            out: dict[str, str] = {}
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    fh = tar.extractfile(member)
                    if fh is None:
                        continue
                    rel = member.name.lstrip("./")
                    out[rel] = fh.read().decode(errors="replace")
            return out
        finally:
            helper.remove(force=True)

    # ------------------------------------------------------------------
    # Workload containers
    # ------------------------------------------------------------------

    def create_workload(
        self,
        suffix: str,
        volumes: dict[str, str],
        labels: dict[str, str],
        running: bool = True,
    ):
        """Create a container that holds volumes and carries dvbm labels.

        The command traps SIGTERM and exits immediately. A bare `sleep` ignores
        SIGTERM, so Docker would wait out the full 30s stop timeout before
        SIGKILL — turning every backup in the suite into a 30-second test. Real
        applications handle SIGTERM, so this is also the more realistic
        workload.
        """
        container = self.client.containers.create(
            WORKLOAD_IMAGE,
            command=["sh", "-c", 'trap "exit 0" TERM; while :; do sleep 1; done'],
            name=self.name(suffix),
            labels=labels,
            volumes={v: {"bind": mount, "mode": "rw"} for v, mount in volumes.items()},
        )
        self._containers.append(container)
        if running:
            container.start()
        return container

    def container_status(self, container) -> str:
        container.reload()
        return container.status

    # ------------------------------------------------------------------
    # Storage services
    # ------------------------------------------------------------------

    def start_minio(self) -> dict:
        """Start MinIO and create the test bucket. Returns an s3 storage config."""
        port = free_port()
        container = self.client.containers.run(
            MINIO_IMAGE,
            command=["server", "/data", "--address", ":9000"],
            name=self.name("minio"),
            environment={
                "MINIO_ROOT_USER": MINIO_USER,
                "MINIO_ROOT_PASSWORD": MINIO_PASSWORD,
            },
            ports={"9000/tcp": ("127.0.0.1", port)},
            detach=True,
        )
        self._containers.append(container)

        endpoint = f"http://127.0.0.1:{port}"
        import boto3
        from botocore.config import Config as BotoConfig

        def _ready():
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=MINIO_USER,
                aws_secret_access_key=MINIO_PASSWORD,
                region_name="us-east-1",
                config=BotoConfig(
                    retries={"max_attempts": 1},
                    connect_timeout=2,
                    read_timeout=2,
                ),
            )
            s3.list_buckets()
            return s3

        s3 = wait_for(_ready, timeout=90, what="MinIO to accept connections")
        s3.create_bucket(Bucket=MINIO_BUCKET)

        # Key names must match what StorageService._s3_client reads.
        return {
            "bucket": MINIO_BUCKET,
            "region": "us-east-1",
            "endpoint_url": endpoint,
            "access_key_id": MINIO_USER,
            "secret_access_key": MINIO_PASSWORD,
            "prefix": "",
        }

    def start_sftp(self) -> dict:
        """Start an SFTP server. Returns an ftp-type storage config in SFTP mode."""
        port = free_port()
        container = self.client.containers.run(
            SFTP_IMAGE,
            command=[f"{SFTP_USER}:{SFTP_PASSWORD}:::upload"],
            name=self.name("sftp"),
            ports={"22/tcp": ("127.0.0.1", port)},
            detach=True,
        )
        self._containers.append(container)

        def _ready():
            with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
                banner = sock.recv(64)
            return banner.startswith(b"SSH-")

        wait_for(_ready, timeout=90, what="SFTP server to accept connections")
        # The banner appears slightly before the server will complete a full
        # key exchange; a brief settle avoids a flaky first connection.
        time.sleep(1.0)

        # The atmoz/sftp user is chrooted, so /upload is the writable dir.
        return {
            "host": "127.0.0.1",
            "port": port,
            "username": SFTP_USER,
            "password": SFTP_PASSWORD,
            "path": "/upload",
            "use_sftp": True,
        }

    def write_rclone_config(self, s3_config: dict) -> tuple[str, dict]:
        """Write an rclone config pointing at MinIO.

        Returns (config path, rclone storage config).
        """
        remote = "testremote"
        config_path = self.tmp_path / "rclone.conf"
        config_path.write_text(
            f"[{remote}]\n"
            "type = s3\n"
            "provider = Minio\n"
            "env_auth = false\n"
            f"access_key_id = {s3_config['access_key_id']}\n"
            f"secret_access_key = {s3_config['secret_access_key']}\n"
            f"endpoint = {s3_config['endpoint_url']}\n"
            "region = us-east-1\n"
            "force_path_style = true\n"
        )
        return str(config_path), {
            "remote_name": remote,
            "path": f"{MINIO_BUCKET}/rclone",
        }

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove everything this environment created. Never raises."""
        for container in self._containers:
            try:
                container.remove(force=True)
            except Exception:
                pass
        # Volumes can briefly stay busy after their containers are removed.
        for vol in self._volumes:
            for attempt in range(5):
                try:
                    self.client.volumes.get(vol).remove(force=True)
                    break
                except docker.errors.NotFound:
                    break
                except Exception:
                    time.sleep(0.4)

        # Sweep anything else carrying our prefix (helper containers created by
        # the app itself, or leftovers from an earlier interrupted run).
        try:
            for c in self.client.containers.list(all=True):
                if c.name and c.name.startswith(f"{PREFIX}-{self.run_id}"):
                    try:
                        c.remove(force=True)
                    except Exception:
                        pass
        except Exception:
            pass


def ensure_images(client, images: list[str]) -> None:
    """Pull any of *images* that are not already present locally.

    Done up front so a slow first pull is not mistaken for a hanging test.
    """
    for ref in images:
        try:
            client.images.get(ref)
        except docker.errors.ImageNotFound:
            repo, _, tag = ref.partition(":")
            client.images.pull(repo, tag=tag or "latest")


def docker_available() -> tuple[bool, str]:
    """Return (available, reason) for the Docker daemon."""
    try:
        client = docker.from_env()
        client.ping()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def rclone_available() -> bool:
    try:
        result = subprocess.run(
            ["rclone", "version"], capture_output=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False
