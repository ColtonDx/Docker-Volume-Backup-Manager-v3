"""Docker integration service.

Communicates with the Docker daemon via the Docker SDK to:
 - List / inspect containers
 - Find containers matching a dvbm label
 - Stop and restart containers
 - List volumes for containers
 - Export / import volume data via temporary helper containers
"""

from __future__ import annotations

import logging
import os
import shutil
import tarfile
import tempfile
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class DockerService:
    """Wrapper around the Docker SDK client."""

    # Short TTL cache for the container listing. GET /api/jobs calls this on
    # every request and several pages poll that endpoint, so without a cache
    # each poll is a full list-with-attrs against the daemon.
    _LIST_CACHE_TTL = 3.0

    def __init__(self) -> None:
        self._client = None
        self._list_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._list_lock = threading.Lock()

    @property
    def client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except Exception as exc:
                logger.warning("Docker not available: %s", exc)
        return self._client

    # ------------------------------------------------------------------
    # Container helpers
    # ------------------------------------------------------------------

    def list_containers(self, all: bool = True) -> list[dict[str, Any]]:
        """Return simplified container info dicts (cached for _LIST_CACHE_TTL)."""
        if not self.client:
            return []

        if all:
            with self._list_lock:
                cached = self._list_cache
                if cached and (time.monotonic() - cached[0]) < self._LIST_CACHE_TTL:
                    return cached[1]

        try:
            containers = self.client.containers.list(all=all)
            result = [self._container_to_dict(c) for c in containers]
        except Exception as exc:
            logger.error("Failed to list containers: %s", exc)
            return []

        if all:
            with self._list_lock:
                self._list_cache = (time.monotonic(), result)
        return result

    def invalidate_container_cache(self) -> None:
        """Drop the cached listing after an operation that changes container state."""
        with self._list_lock:
            self._list_cache = None

    def find_containers_by_label(self, label_key: str, label_value: str) -> list[dict[str, Any]]:
        """Find containers with a specific label key=value."""
        if not self.client:
            return []
        try:
            containers = self.client.containers.list(
                all=True,
                filters={"label": f"{label_key}={label_value}"},
            )
            return [self._container_to_dict(c) for c in containers]
        except Exception as exc:
            logger.error("Failed to find containers by label: %s", exc)
            return []

    def stop_containers(self, container_ids: list[str], timeout: int = 30) -> list[str]:
        """Stop containers by ID. Returns list of successfully stopped IDs.

        Raises RuntimeError if any container could not be stopped: backing up a
        volume while its container is still writing to it produces an archive
        that typically restores as a corrupt database.
        """
        stopped: list[str] = []
        failed: list[str] = []
        if not self.client:
            return stopped
        for cid in container_ids:
            try:
                container = self.client.containers.get(cid)
                if container.status == "running":
                    container.stop(timeout=timeout)
                    stopped.append(cid)
                    logger.info("Stopped container %s", cid)
            except Exception as exc:
                logger.error("Failed to stop container %s: %s", cid, exc)
                failed.append(cid)
        self.invalidate_container_cache()
        if failed:
            # Restart whatever we already stopped so we do not leave the user's
            # containers down after aborting.
            if stopped:
                self.start_containers(stopped)
            raise RuntimeError(
                f"Could not stop container(s): {', '.join(failed)}. "
                "Aborting to avoid taking a backup of live, in-use volumes."
            )
        return stopped

    def start_containers(self, container_ids: list[str]) -> list[str]:
        """Start containers by ID. Returns list of successfully started IDs."""
        started = []
        if not self.client:
            return started
        for cid in container_ids:
            try:
                container = self.client.containers.get(cid)
                if container.status != "running":
                    container.start()
                    started.append(cid)
                    logger.info("Started container %s", cid)
            except Exception as exc:
                logger.error("Failed to start container %s: %s", cid, exc)
        self.invalidate_container_cache()
        return started

    def get_container_volumes(self, container_id: str) -> list[dict[str, str]]:
        """Return list of named volume mounts for a container."""
        if not self.client:
            return []
        try:
            container = self.client.containers.get(container_id)
            mounts = container.attrs.get("Mounts", [])
            volumes = []
            for m in mounts:
                if m.get("Type") == "volume":
                    volumes.append({
                        "name": m.get("Name", ""),
                        "source": m.get("Source", ""),
                        "destination": m.get("Destination", ""),
                    })
            return volumes
        except Exception as exc:
            logger.error("Failed to get volumes for container %s: %s", container_id, exc)
            return []

    def get_volume_path(self, volume_name: str) -> str | None:
        """Get the host-side path of a Docker volume."""
        if not self.client:
            return None
        try:
            vol = self.client.volumes.get(volume_name)
            return vol.attrs.get("Mountpoint")
        except Exception as exc:
            logger.error("Failed to get volume path for %s: %s", volume_name, exc)
            return None

    # ------------------------------------------------------------------
    # Volume export / import (works from inside a container)
    # ------------------------------------------------------------------

    HELPER_IMAGE = "alpine:3.20"

    def _ensure_helper_image(self) -> None:
        """Pull the helper image if it isn't already present."""
        if not self.client:
            return
        try:
            self.client.images.get(self.HELPER_IMAGE)
        except Exception:
            logger.info("Pulling helper image %s ...", self.HELPER_IMAGE)
            self.client.images.pull(*self.HELPER_IMAGE.split(":"))

    def export_volume(self, volume_name: str, dest_dir: str) -> str | None:
        """Export a named Docker volume's contents into *dest_dir*/<volume_name>/.

        Spins up a temporary ``alpine`` container that mounts the volume
        read-only and streams its contents back as a tar archive via the
        Docker ``get_archive`` API.  This works even when dvbm
        itself is running inside a container (i.e. no host filesystem
        access).

        Returns the path to the extracted directory, or None on failure.
        """
        if not self.client:
            return None

        container = None
        out_path = os.path.join(dest_dir, volume_name)
        os.makedirs(out_path, exist_ok=True)

        try:
            self._ensure_helper_image()

            # Create (don't start) a disposable container with the volume mounted
            container = self.client.containers.create(
                self.HELPER_IMAGE,
                command="true",
                volumes={volume_name: {"bind": "/volume_data", "mode": "ro"}},
            )

            # get_archive streams a tar of /volume_data/.  The paths
            # inside the tar start with "volume_data/…".
            bits, _stat = container.get_archive("/volume_data/.")
            # Spool the stream to disk rather than joining it in memory: a
            # multi-GB volume would otherwise be held in RAM twice over.
            from app.services.tar_utils import safe_extractall
            with tempfile.NamedTemporaryFile(
                dir=dest_dir, prefix=".export_", suffix=".tar"
            ) as spool:
                for chunk in bits:
                    spool.write(chunk)
                spool.flush()
                spool.seek(0)
                with tarfile.open(fileobj=spool, mode="r") as tar:
                    safe_extractall(tar, out_path)

            logger.info("Exported volume %s -> %s", volume_name, out_path)
            return out_path

        except Exception as exc:
            logger.error("Failed to export volume %s: %s", volume_name, exc)
            # Remove the directory created up front, otherwise a failed export
            # is indistinguishable from a backup of a genuinely empty volume.
            shutil.rmtree(out_path, ignore_errors=True)
            return None
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def import_volume(self, volume_name: str, source_dir: str) -> bool:
        """Import contents of *source_dir* into a named Docker volume.

        Spins up a temporary ``alpine`` container with the volume mounted
        read-write, clears existing data, and uploads a tar of
        *source_dir* into it via ``put_archive``.
        """
        if not self.client:
            return False

        container = None
        try:
            self._ensure_helper_image()

            # Build the tar BEFORE clearing the volume. If archive creation
            # fails we must not have destroyed the existing data already.
            # Spooled to disk so a large volume does not sit in RAM twice.
            with tempfile.NamedTemporaryFile(prefix=".import_", suffix=".tar") as spool:
                with tarfile.open(fileobj=spool, mode="w") as tar:
                    for entry in os.listdir(source_dir):
                        full = os.path.join(source_dir, entry)
                        tar.add(full, arcname=entry)
                spool.flush()
                spool.seek(0)

                # Clear existing volume data with a disposable container
                self.client.containers.run(
                    self.HELPER_IMAGE,
                    command=["sh", "-c", "rm -rf /volume_data/* /volume_data/.[!.]* 2>/dev/null; true"],
                    volumes={volume_name: {"bind": "/volume_data", "mode": "rw"}},
                    remove=True,
                )

                # Create (don't start) a helper container with the volume mounted.
                # Keeping the container in "created" state ensures the volume
                # mount is active for put_archive (same pattern as export_volume).
                container = self.client.containers.create(
                    self.HELPER_IMAGE,
                    command="true",
                    volumes={volume_name: {"bind": "/volume_data", "mode": "rw"}},
                )

                # Upload into the volume via the helper container. Passing the
                # file object streams it instead of copying it into memory.
                container.put_archive("/volume_data", spool)

            # Verify data was written by checking the volume
            verify = self.client.containers.run(
                self.HELPER_IMAGE,
                command=["sh", "-c", "ls -A /volume_data | head -5"],
                volumes={volume_name: {"bind": "/volume_data", "mode": "ro"}},
                remove=True,
            )
            if not verify or not verify.strip():
                logger.warning("Volume %s appears empty after import", volume_name)
                return False

            logger.info("Imported %s -> volume %s", source_dir, volume_name)
            return True

        except Exception as exc:
            logger.error("Failed to import into volume %s: %s", volume_name, exc)
            return False
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _container_to_dict(container) -> dict[str, Any]:
        mounts = container.attrs.get("Mounts", [])
        volume_names = [
            m.get("Name", m.get("Source", ""))
            for m in mounts
            if m.get("Type") == "volume"
        ]
        name = container.name or ""
        if name.startswith("/"):
            name = name[1:]
        return {
            "id": container.short_id,
            "name": name,
            "image": container.image.tags[0] if container.image.tags else str(container.image.id)[:12],
            "status": container.status,
            "labels": dict(container.labels or {}),
            "volumes": volume_names,
        }


docker_service = DockerService()
