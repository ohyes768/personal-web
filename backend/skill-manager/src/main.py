"""skill-manager FastAPI 入口（design 7）。

注意：Settings 不在模块导入时实例化——import app 不应要求环境变量已就绪。
lifespan 在应用启动时从环境变量构造 Settings 并初始化各 service 单例
（挂到 app.state，路由经 src.api.dependencies 定位）；测试可用
dependency_overrides 替换任意服务（如离线 remotes 的 GitCacheService）。

错误契约（design 7）：HTTPException 的 dict detail 展平为顶层
`{"code", "message"}`；请求体校验失败统一 400 `invalid_request`。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.config import Settings
from src.db import SkillStateStore
from src.services.git_cache import GitCacheService, cleanup_stale_workspaces
from src.services.publisher import Publisher
from src.services.registry import RegistryService
from src.services.task_manager import GithubTaskManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    store = SkillStateStore.from_settings(settings)
    app.state.settings = settings
    app.state.store = store
    app.state.registry = RegistryService(store, settings.skills_source_root)
    app.state.publisher = Publisher(settings, store)
    app.state.git_cache = GitCacheService(settings, store)
    # GitHub 后台任务表：与 git_cache 共享同一单例，测试对 get_git_cache
    # / get_task_manager 做 dependency_overrides 时需一并注入同源实例
    app.state.task_manager = GithubTaskManager(app.state.git_cache, app.state.registry)
    # 进程重启遗留的扫描工作区 / clone 临时目录（孤儿）在启动时清空；
    # 失败仅记日志，不阻断启动（PRD R8 / design §4）
    cleanup_stale_workspaces(settings)
    business_logger = logging.getLogger("src")
    business_logger.setLevel(logging.INFO)
    if not business_logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        business_logger.addHandler(handler)
    yield


app = FastAPI(title="skill-manager", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """把 dict detail 展平为顶层错误契约；非 dict detail 兜底包装。"""
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "error", "message": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """请求体/参数校验失败统一 400（design 7：非法 id/path/target → 400）。"""
    return JSONResponse(
        status_code=400,
        content={"code": "invalid_request", "message": "请求参数不合法"},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    """存活探针：无依赖、无状态。"""
    return {"status": "ok"}
