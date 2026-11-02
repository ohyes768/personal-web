"""FastAPI 应用入口。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import __version__
from src.api.routes import router
from src.config import get_settings
from src.services.notifier import DingTalkNotifier
from src.services.report_service import ReportService
from src.services.scheduler import JOB_WEEKLY, ReportScheduler
from src.services.store import Store
from src.services.trend_service import WeeklyTrendService
from src.services.valuation_service import ValuationService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("index-trends")


def create_app() -> FastAPI:
    settings = get_settings()
    store = Store(settings.data_dir / "index-trends.db")
    trend_service = WeeklyTrendService(store)
    notifier = DingTalkNotifier()
    valuation_service = ValuationService(
        store,
        token=settings.lixinger_token.get_secret_value(),
        calendar=trend_service.trading_calendar,
    )
    report_service = ReportService(
        store,
        trend_service,
        notifier,
        settings.public_site_url,
        valuation_service=valuation_service,
    )

    async def weekly_job() -> dict:
        async with trend_service.refresh_lock:
            return await asyncio.to_thread(report_service.run_weekly_sync)

    async def daily_job() -> object:
        try:
            return await trend_service.refresh()
        finally:
            # 估值采集独立于行情：行情失败也尽量采集，估值失败不改行情语义
            await _refresh_valuation(valuation_service)

    scheduler = ReportScheduler(
        weekly_fn=weekly_job,
        refresh_fn=daily_job,
        report_cron=settings.report_cron,
        daily_cron=settings.daily_refresh_cron,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler.start()
        app.state.scheduler = scheduler
        app.state.trend_service = trend_service
        app.state.valuation_service = valuation_service
        # 启动补发检查：已过本周五 19:00 且本周未 sent → 幂等补跑
        catchup = asyncio.create_task(
            _catchup_with_lock(report_service, trend_service)
        )
        # 启动估值初始化：与补发共用生命周期任务，失败不阻断启动
        valuation_init = asyncio.create_task(_refresh_valuation(valuation_service))
        logger.info("index-trends %s 启动，数据目录 %s", __version__, settings.data_dir)
        yield
        catchup.cancel()
        valuation_init.cancel()
        try:
            await catchup  # 等取消落地，避免事件循环关闭时任务仍挂起
        except asyncio.CancelledError:
            pass
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


async def _catchup_with_lock(report_service: ReportService, trend_service: WeeklyTrendService) -> None:
    async with trend_service.refresh_lock:
        await asyncio.to_thread(report_service.catchup_if_needed)


async def _refresh_valuation(valuation_service: ValuationService) -> None:
    """采集估值（尽力而为）：异常只记录，不影响行情与周报。"""
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
