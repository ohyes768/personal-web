"""service-manager FastAPI 入口（design §2）。

- Settings 不在导入时实例化：import 本模块不应要求环境变量就绪
- lifespan 构造 Settings + 各 service 单例并挂到 app.state
- 生产环境缺密码/签名密钥 → 拒绝启动
- 错误契约：`{code, message, field_errors?}`；校验失败统一 400
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.routes import router
from src.auth import AuthService
from src.checker import Checker
from src.checks.common import CheckStore
from src.checks.github import GithubClient, ReleaseStore
from src.checks.http_probe import ProbeConfig
from src.config import Settings
from src.db import Store
from src.discovery import DiscoveryService
from src.docker_reader import DockerClient
from src.errors import ApiError
from src.jobs import JobManager
from src.models import RefreshKind
from src.registry import Registry
from src.resources import ResourceProjector
from src.status import StatusProjector

logger = logging.getLogger(__name__)


def build_app(settings: Settings) -> FastAPI:
    """构造应用（测试可传自己的 Settings，无需环境变量）。"""
    store = Store.from_settings(settings)
    registry = Registry(store)
    # 旧库没有归属列：按旧分组口径回填一次（已判定的不动）
    registry.backfill_ownership(settings.own_project_list)
    reader = (
        DockerClient(settings.docker_host, timeout=settings.docker_timeout)
        if settings.docker_host
        else None
    )
    discovery = DiscoveryService(store, registry, reader)
    releases = ReleaseStore(store)
    checks = CheckStore(store)
    github = (
        GithubClient(
            token=settings.github_token.get_secret_value()
            if settings.github_token
            else None
        )
        if True
        else None
    )
    checker = Checker(
        registry=registry,
        discovery=discovery,
        checks=checks,
        releases=releases,
        github=github,
        probe_config=ProbeConfig(),
        intervals={
            "url": settings.url_interval,
            "tls": settings.tls_interval,
            "releases": settings.release_interval,
            "docker": settings.docker_interval,
        },
    )
    jobs = JobManager(store)
    for kind in (
        RefreshKind.DOCKER,
        RefreshKind.URL,
        RefreshKind.TLS,
        RefreshKind.RELEASES,
        RefreshKind.ALL,
    ):
        jobs.register(kind, checker.run_kind)

    auth = AuthService(
        password=settings.admin_password.get_secret_value(),
        secret=settings.session_secret.get_secret_value(),
        session_hours=settings.session_hours,
        secure_cookie=settings.secure_cookie,
        origin_allowlist=settings.origin_allowlist,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        jobs.recover_interrupted()
        jobs.prune()
        app.state.stop = asyncio.Event()
        if settings.scheduler_enabled:
            app.state.scheduler_task = asyncio.create_task(
                checker.scheduler_loop(stop=app.state.stop)
            )
        if settings.docker_host:
            asyncio.create_task(asyncio.to_thread(discovery.run_scan))
        logger.info(
            "service-manager started (data=%s, docker=%s, scheduler=%s)",
            settings.data_dir,
            bool(settings.docker_host),
            settings.scheduler_enabled,
        )
        try:
            yield
        finally:
            app.state.stop.set()
            task = getattr(app.state, "scheduler_task", None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    app = FastAPI(title="service-manager", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.registry = registry
    app.state.discovery = discovery
    app.state.jobs = jobs
    app.state.checker = checker
    app.state.auth = auth
    app.state.releases = releases
    app.state.checks = checks
    app.state.resources = ResourceProjector(registry, discovery)
    app.state.status = StatusProjector(registry, discovery, releases)
    app.include_router(router)
    _install_error_handlers(app)
    return app


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        body: dict[str, object] = {"code": exc.code, "message": exc.message}
        if exc.field_errors:
            body["field_errors"] = exc.field_errors
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
            413: "payload_too_large",
            429: "rate_limited",
            503: "dependency_unavailable",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors: dict[str, str] = {}
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", ())[1:]) or "body"
            field_errors[location] = str(error.get("msg", "不合法"))
        return JSONResponse(
            status_code=400,
            content={
                "code": "invalid_request",
                "message": "请求参数不合法",
                "field_errors": field_errors,
            },
        )


def create_app() -> FastAPI:
    """uvicorn 入口：这里才读环境变量（缺失则启动失败）。"""
    return build_app(Settings())


_app: FastAPI | None = None


def __getattr__(name: str):
    """惰性构造 `src.main:app`，避免导入期就要求环境变量。

    模块级不能写 `app = None`——那会让 uvicorn 直接拿到 None，
    这里用 `__getattr__` 在首次访问时构造（uvicorn 的 import_from_string
    走 getattr，未命中的属性才会触发本函数）。
    """
    if name == "app":
        global _app
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
