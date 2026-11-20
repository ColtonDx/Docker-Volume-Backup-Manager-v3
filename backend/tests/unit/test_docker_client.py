"""Docker client endpoint selection (no daemon needed; docker module mocked)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture
def fake_docker(monkeypatch):
    mod = MagicMock()
    monkeypatch.setitem(sys.modules, "docker", mod)
    return mod


def _settings(monkeypatch, socket):
    from app.config import settings

    monkeypatch.setattr(settings, "DOCKER_SOCKET", socket)


def test_docker_socket_used_when_docker_host_unset(fake_docker, monkeypatch):
    from app.services.docker_service import create_docker_client

    monkeypatch.delenv("DOCKER_HOST", raising=False)
    _settings(monkeypatch, "tcp://docker-socket-proxy:2375")

    client = create_docker_client()

    fake_docker.DockerClient.assert_called_once_with(base_url="tcp://docker-socket-proxy:2375")
    fake_docker.from_env.assert_not_called()
    assert client is fake_docker.DockerClient.return_value


def test_docker_host_takes_precedence(fake_docker, monkeypatch):
    from app.services.docker_service import create_docker_client

    monkeypatch.setenv("DOCKER_HOST", "tcp://elsewhere:2376")
    _settings(monkeypatch, "tcp://docker-socket-proxy:2375")

    client = create_docker_client()

    fake_docker.from_env.assert_called_once_with()
    fake_docker.DockerClient.assert_not_called()
    assert client is fake_docker.from_env.return_value


def test_default_is_unix_socket(fake_docker, monkeypatch):
    from app.config import Settings
    from app.services.docker_service import create_docker_client

    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_SOCKET", raising=False)
    _settings(monkeypatch, Settings().DOCKER_SOCKET)

    create_docker_client()

    fake_docker.DockerClient.assert_called_once_with(base_url="unix:///var/run/docker.sock")


def test_service_client_uses_helper(fake_docker, monkeypatch):
    from app.services.docker_service import DockerService

    monkeypatch.delenv("DOCKER_HOST", raising=False)
    _settings(monkeypatch, "unix:///tmp/x.sock")

    svc = DockerService()
    assert svc.client is fake_docker.DockerClient.return_value
    fake_docker.DockerClient.assert_called_once_with(base_url="unix:///tmp/x.sock")
