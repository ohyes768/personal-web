"""依赖注入（design §2 / §7）。

所有 service 单例挂在 app.state，路由经这里定位；测试用 dependency_overrides
替换任意服务，无需真实 Docker / GitHub / 网络。
"""

from __future__ import annotations

from fastapi import Request

from src.auth import AuthService
from src.backup import Preview
from src.checker import Checker
from src.config import Settings
from src.db import Store
from src.discovery import DiscoveryService
from src.jobs import JobManager
from src.registry import Registry
from src.resources import ResourceProjector
from src.status import StatusProjector


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_auth(request: Request) -> AuthService:
    return request.app.state.auth


def get_registry(request: Request) -> Registry:
    return request.app.state.registry


def get_discovery(request: Request) -> DiscoveryService:
    return request.app.state.discovery


def get_jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def get_checker(request: Request) -> Checker:
    return request.app.state.checker


def get_resources(request: Request) -> ResourceProjector:
    return request.app.state.resources


def get_status_projector(request: Request) -> StatusProjector:
    return request.app.state.status
