"""Docker integration service.

Communicates with the Docker daemon via the Docker SDK to:
 - List / inspect containers
 - Find containers matching a backup-buddy label
 - Stop and restart containers
 - List volumes for containers
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DockerService:
    """Wrapper around the Docker SDK client."""

    def __init__(self) -> None:
        self._client = None

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
        """Return simplified container info dicts."""
        if not self.client:
            return []
        try:
            containers = self.client.containers.list(all=all)
            return [self._container_to_dict(c) for c in containers]
        except Exception as exc:
            logger.error("Failed to list containers: %s", exc)
            return []

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
        """Stop containers by ID. Returns list of successfully stopped IDs."""
        stopped = []
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
