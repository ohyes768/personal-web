"""FastAPI 依赖：从 `app.state` 定位服务单例与管理密码守卫（design 7 / R5）。

服务单例由 `main.lifespan` 从 Settings 构造并挂到 `app.state`；测试可用
`app.dependency_overrides` 替换任意 getter（例如注入离线 remotes 的
GitCacheService）。

密码守卫 `ensure_admin_password()` 使用 `hmac.compare_digest` 常量时间比较；
失败一律 401 `{"code": "invalid_password", "message": ...}`，绝不回显密码、
绝不持久化。
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from src.config import Settings
from src.db import SkillStateStore
from src.services.git_cache import GitCacheService
from src.services.publisher import Publisher
from src.services.registry import RegistryService
from src.services.task_manager import GithubTaskManager


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> SkillStateStore:
    return request.app.state.store


def get_registry(request: Request) -> RegistryService:
    return request.app.state.registry


def get_publisher(request: Request) -> Publisher:
    return request.app.state.publisher


def get_git_cache(request: Request) -> GitCacheService:
    return request.app.state.git_cache


def get_task_manager(request: Request) -> GithubTaskManager:
    return request.app.state.task_manager


def ensure_admin_password(settings: Settings, submitted: str) -> None:
    """校验管理密码；错误返回 401，请求方传入的密码不记录、不回显。"""
    expected = settings.admin_password.get_secret_value().encode("utf-8")
    actual = submitted.encode("utf-8")
    if not hmac.compare_digest(actual, expected):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_password",
                "message": "管理密码错误，操作已被拒绝",
            },
        )
