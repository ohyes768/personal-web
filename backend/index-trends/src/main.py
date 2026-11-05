"""FastAPI 应用入口。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import __version__
from src.api.routes import router
from src.config import get_settings
from src.services.scheduler import RefreshScheduler
from src.services.store import Store
from src.services.trend_service import WeeklyTrendService
from src.services.valuation_service import ValuationService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("index-trends")


def create_app() -> FastAPI:
    settings = get_settings()
    store = Store(settings.data_dir / "index-trends.db")
    trend_service = WeeklyTrendService(store)
    valuation_service = ValuationService(
        store,
        token=settings.lixinger_token.get_secret_value(),
        calendar=trend_service.trading_calendar,
    )

    async def daily_job() -> object:
        try:
            return await trend_service.refresh()
        finally:
            # 估值采集独立于行情：行情失败也尽量采集，估值失败不改行情语义
            await _refresh_valuation(valuation_service)

    scheduler = RefreshScheduler(
        refresh_fn=daily_job,
        daily_cron=settings.daily_refresh_cron,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler.start()
        app.state.scheduler = scheduler
        app.state.trend_service = trend_service
        app.state.valuation_service = valuation_service
        # 启动估值初始化；简报调度与投递由 Hermes 负责。
        valuation_init = asyncio.create_task(_refresh_valuation(valuation_service))
        logger.info("index-trends %s 启动，数据目录 %s", __version__, settings.data_dir)
        yield
        valuation_init.cancel()
        try:
            await valuation_init
        except asyncio.CancelledError:
            pass
        await scheduler.shutdown()
        store.close()
        logger.info("index-trends 已关闭")

    app = FastAPI(title="Index Trends API", version=__version__, lifespan=lifespan)
    app.include_router(router)
    return app


async def _refresh_valuation(valuation_service: ValuationService) -> None:
    """采集估值（尽力而为）：异常只记录，不影响行情。"""
    try:
        await asyncio.to_thread(valuation_service.refresh)
    except Exception as exc:  # noqa: BLE001 — 估值问题不阻断其他链路
        logger.warning("估值采集失败: %s", exc)


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=True,
    )
