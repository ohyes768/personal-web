"""scheduler job 业务实现：HTTP self-call 到本地 /api/dividend/* 接口"""

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from src.scheduler.trading_calendar import is_trading_day
from src.utils.logger import setup_logger

if TYPE_CHECKING:
    from src.scheduler.manager import SchedulerManager

logger = setup_logger(__name__)


async def refresh_realtime(ctx: "SchedulerManager", job_id: str) -> dict[str, Any]:
    """每日刷新实时价格（接口内会顺带触发挡位告警）。"""
    spec = ctx.jobs_meta[job_id]

    if spec.get("check_trading_day") and not is_trading_day():
        logger.info(f"[{job_id}] 非交易日，skip")
        return {"status": "skipped", "reason": "non_trading_day"}

    codes = ctx.get_holdings_codes()
    if not codes:
        logger.warning(f"[{job_id}] 持仓 codes 为空，skip")
        return {"status": "skipped", "reason": "empty_holdings"}

    return await _self_call(
        ctx, job_id, target_path="/realtime/refresh", body={"codes": codes}
    )


async def refresh_m120(ctx: "SchedulerManager", job_id: str) -> dict[str, Any]:
    """每周刷新 M120 数据。"""
    spec = ctx.jobs_meta[job_id]

    if spec.get("check_trading_day") and not is_trading_day():
        logger.info(f"[{job_id}] 非交易日，skip")
        return {"status": "skipped", "reason": "non_trading_day"}

    codes = ctx.get_holdings_codes()
    if not codes:
        logger.warning(f"[{job_id}] 持仓 codes 为空，skip")
        return {"status": "skipped", "reason": "empty_holdings"}

    return await _self_call(
        ctx, job_id, target_path="/m120/refresh", body={"codes": codes}
    )


async def refresh_dividend(ctx: "SchedulerManager", job_id: str) -> dict[str, Any]:
    """每月刷新股息率核心数据。撞到 _is_refreshing 锁时记 skipped。"""
    spec = ctx.jobs_meta[job_id]
    params = spec.get("params") or {}
    return await _self_call(
        ctx,
        job_id,
        target_path="/dividend/refresh",
        body=params,
        interpret_409_as_skipped=True,
    )


async def _self_call(
    ctx: "SchedulerManager",
    job_id: str,
    target_path: str,
    body: dict,
    interpret_409_as_skipped: bool = False,
) -> dict[str, Any]:
    """HTTP self-call 到本地接口。返回 record dict（status/count/error/start/end）。"""
    start = datetime.now()
    url = f"http://127.0.0.1:{ctx.port}/api/dividend{target_path}"
    logger.info(f"[{job_id}] self-call POST {url} body_keys={list(body.keys())}")
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(url, json=body)
            if resp.status_code == 202:
                data = resp.json()
                record = {'start': start.isoformat(), 'refresh_job_id': data['job_id']}
                if data.get('reused'):
                    return {**record, 'status': 'skipped', 'reason': 'already_running', 'end': datetime.now().isoformat()}
                deadline = time.monotonic() + 3600
                while time.monotonic() < deadline:
                    query = await client.get(f"http://127.0.0.1:{ctx.port}/api/dividend/refresh/jobs/{data['job_id']}", timeout=15)
                    query.raise_for_status()
                    job = query.json()
                    if job['status'] not in ('queued', 'running'):
                        return {**record, 'status': 'success' if job['status'] == 'succeeded' else job['status'],
                                'count': job.get('succeeded'), 'failed': job.get('failed'),
                                'remaining': job.get('remaining'), 'error': job.get('error'),
                                'end': datetime.now().isoformat()}
                    await asyncio.sleep(2)
                raise TimeoutError('等待后台刷新超时；采集可能仍在运行')
    except Exception as e:
        logger.error(f"[{job_id}] self-call 网络异常: {e}")
        return {
            "status": "failed",
            "error": f"httpx error: {e}",
            "start": start.isoformat(),
            "end": datetime.now().isoformat(),
        }

    end = datetime.now()

    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception:
            data = {}
        return {
            "status": "success",
            "count": data.get("count"),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    if resp.status_code == 409 and interpret_409_as_skipped:
        logger.warning(f"[{job_id}] 目标接口忙（409 already_running），skip")
        return {
            "status": "skipped",
            "reason": "already_running",
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    return {
        "status": "failed",
        "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


# target 字段 → 函数映射
JOB_TARGETS = {
    "refresh_realtime": refresh_realtime,
    "refresh_m120": refresh_m120,
    "refresh_dividend": refresh_dividend,
}
