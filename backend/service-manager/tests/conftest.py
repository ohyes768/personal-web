"""pytest 公共夹具。

设计约束（design §7）：
- 不依赖真实 Docker / GitHub / 网络：所有外部依赖用注入的假实现
- pytest basetemp 固定在仓库内（Windows %TEMP% 上 os.replace 报 WinError 6）
- 每次测试独立的 SQLite 文件
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("SERVICE_MANAGER_ADMIN_PASSWORD", "test-password")
os.environ.setdefault("SERVICE_MANAGER_SESSION_SECRET", "test-secret")
os.environ.setdefault("SERVICE_MANAGER_SCHEDULER_ENABLED", "false")

from src.config import Settings  # noqa: E402
from src.db import Store  # noqa: E402
from src.discovery import DiscoveryService  # noqa: E402
from src.registry import Registry  # noqa: E402


class FakeReader:
    """可控的 Docker 读取器。"""

    def __init__(self, payloads: list[dict[str, Any]] | None = None) -> None:
        self.payloads = payloads or []
        self.fail_with: Exception | None = None
        self.calls = 0

    def list_containers(self) -> list[dict[str, Any]]:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        return self.payloads


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        SERVICE_MANAGER_ADMIN_PASSWORD="test-password",
        SERVICE_MANAGER_SESSION_SECRET="test-secret",
        SERVICE_MANAGER_DATA_DIR=tmp_path / "data",
        SERVICE_MANAGER_PUBLIC_ORIGIN="http://localhost:3012",
        SERVICE_MANAGER_SECURE_COOKIE="false",
        SERVICE_MANAGER_SCHEDULER_ENABLED="false",
        SERVICE_MANAGER_DOCKER_HOST="",
    )


@pytest.fixture()
def store(settings: Settings) -> Store:
    return Store.from_settings(settings)


@pytest.fixture()
def registry(store: Store) -> Registry:
    return Registry(store)


@pytest.fixture()
def discovery(store: Store, registry: Registry) -> DiscoveryService:
    return DiscoveryService(store, registry, None)


def container_payload(
    *,
    project: str | None = "personal-web",
    service: str | None = "dividend",
    number: str = "1",
    container_id: str = "a" * 64,
    name: str | None = None,
    image: str = "dividend-frontend:latest",
    state: str = "running",
    health_status: str | None = "",
    network_mode: str = "bridge",
    ports: dict[str, Any] | None = None,
    mounts: list[dict[str, Any]] | None = None,
    working_dir: str | None = "/home/ohyes768/personal-web",
    config_files: str | None = "docker-compose.nas.yml",
    oneoff: bool = False,
) -> dict[str, Any]:
    labels: dict[str, str] = {}
    if project:
        labels["com.docker.compose.project"] = project
    if service:
        labels["com.docker.compose.service"] = service
        labels["com.docker.compose.container-number"] = number
    if working_dir:
        labels["com.docker.compose.project.working_dir"] = working_dir
    if config_files:
        labels["com.docker.compose.project.config_files"] = config_files
    if oneoff:
        labels["com.docker.compose.oneoff"] = "true"
    state_block: dict[str, Any] = {"Status": state}
    if health_status is not None:
        state_block["Health"] = {"Status": health_status}
    return {
        "Id": container_id,
        "Name": f"/{name or f'{project}-{service}-{number}'}",
        "Config": {"Image": image, "Labels": labels},
        "Image": "sha256:" + "b" * 64,
        "State": state_block,
        "HostConfig": {"NetworkMode": network_mode},
        "NetworkSettings": {
            "Ports": ports if ports is not None else {},
            "Networks": {"nginx_nginx-bridge": {"IPAddress": "172.18.0.5"}},
        },
        "Mounts": mounts or [],
    }
