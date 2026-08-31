"""scheduler job 业务实现：组任务顺序 HTTP self-call 到本地 /api/update/* 接口

与 dividend-select 的单 target self-call 不同：宏观一个 job = 一组有序的
update 端点，逐个顺序执行并聚合结果。macro 的 update 端点返回
HTTP 200 + body{success, message, data?}（success=False 表业务失败），
按 body.success 判定成败，无 409 特判。
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from src.scheduler.timezone import now_shanghai
from src.scheduler.trading_calendar import is_trading_day
from src.utils.logger import setup_logger

if TYPE_CHECKING:
    from src.scheduler.manager import SchedulerManager

logger = setup_logger("scheduler")


async def run_group(ctx: "SchedulerManager", job_id: str) -> dict[str, Any]:
    """组任务执行器：按 spec["targets"] 顺序 self-call 一组 update 端点。

    - 单个数据源失败不中断组内后续数据源的执行（每源独立记 item）
    - 聚合：全 success → success；有成功有失败 → partial；全失败 → failed
    - 返回 record dict（status/count/items/start/end），items 随历史落盘
    """
    spec = ctx.jobs_meta[job_id]
    start = now_shanghai()

    if spec.get("check_trading_day") and not is_trading_day():
        logger.info(f"[{job_id}] 非交易日，skip date={now_shanghai().date().isoformat()}")
        return {
            "status": "skipped",
            "reason": "non_trading_day",
            "start": start.isoformat(),
            "end": now_shanghai().isoformat(),
        }

    targets = spec.get("targets") or []
    if not targets:
        logger.error(f"[{job_id}] targets 为空，无可执行数据源")
        return {
            "status": "failed",
            "error": "targets 为空，无可执行数据源",
            "count": 0,
            "items": [],
            "start": start.isoformat(),
            "end": now_shanghai().isoformat(),
        }

    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=600) as client:
        for path in targets:
            item = await _self_call_one(client, ctx.port, path)
            items.append(item)
            logger.info(
                f"[{job_id}] {path} → {item['status']}"
                + (f" error={item['error']}" if item.get("error") else "")
            )

    ok_count = sum(1 for it in items if it["status"] == "success")
    if ok_count == len(items):
        status = "success"
    elif ok_count == 0:
        status = "failed"
    else:
        status = "partial"

    return {
        "status": status,
        "count": ok_count,
        "items": items,
        "start": start.isoformat(),
        "end": now_shanghai().isoformat(),
    }


async def _self_call_one(
    client: httpx.AsyncClient, port: int, path: str
) -> dict[str, Any]:
    """单个 update 端点 self-call。返回 item dict（path/status/count/ms/error）。

    - 200 且 body.success=True → success（count 取 data 条数，data 非列表时为 None）
    - 200 但 body.success=False → failed，记 body.message；继续下一个
    - 非 200 / 网络异常 / 超时 → failed；继续下一个（单源失败不中断）
    """
    t0 = now_shanghai()
    url = f"http://127.0.0.1:{port}/api{path}"
    try:
        resp = await client.post(url)
    except Exception as e:
        logger.error(f"{path} self-call 网络异常: {e}")
        return {
            "path": path,
            "status": "failed",
            "count": None,
            "ms": _elapsed_ms(t0),
            "error": f"httpx error: {e}",
        }

    ms = _elapsed_ms(t0)
    try:
        body = resp.json()
    except Exception:
        body = {}

    if resp.status_code == 200 and body.get("success") is True:
        return {
            "path": path,
            "status": "success",
            "count": _data_count(body.get("data")),
            "ms": ms,
            "error": None,
        }

    # 200 但 success=False → 业务失败（记 message）；非 200 → HTTP 失败
    error = body.get("message") or f"HTTP {resp.status_code}: {resp.text[:200]}"
    logger.warning(f"{path} 更新失败: {error}")
    return {
        "path": path,
        "status": "failed",
        "count": None,
        "ms": ms,
        "error": error,
    }


def _data_count(data: Any) -> int | None:
    """data 为列表时返回条数；macro 的 data 多为嵌套结构，取不到时返回 None。"""
    if isinstance(data, list):
        return len(data)
    return None


def _elapsed_ms(t0: datetime) -> int:
    return int((now_shanghai() - t0).total_seconds() * 1000)


# target 字段 → 函数映射
JOB_TARGETS = {
    "run_group": run_group,
}
