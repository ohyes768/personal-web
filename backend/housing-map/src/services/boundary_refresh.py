"""地图小区轮廓重建任务。

与价格刷新完全分离：只用现有 OSM 数据重写多边形文件，不访问透明售房网。
"""

import asyncio
from datetime import datetime, timezone
from typing import Callable

from scripts.build_merged_polygons import main as rebuild_osm_boundaries


job: dict = {
    "running": False,
    "phase": "idle",  # idle | rebuilding | done | error
    "startedAt": None,
    "finishedAt": None,
    "error": None,
    "result": None,
}

_task: asyncio.Task | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _watch_rebuild(builder: Callable[[], dict]) -> None:
    global _task
    try:
        job["result"] = await asyncio.to_thread(builder)
        job["phase"] = "done"
    except (OSError, ValueError, KeyError) as error:
        job["phase"] = "error"
        job["error"] = f"轮廓重建失败: {error}"
    finally:
        _task = None
        job["running"] = False
        job["finishedAt"] = _now_iso()


async def start_rebuild(*, builder: Callable[[], dict] = rebuild_osm_boundaries) -> tuple[bool, int, dict]:
    """启动 OSM 轮廓重建；同一时刻只允许一个轮廓任务。"""
    global _task
    if job["running"]:
        return False, 409, {"success": False, "error": "已有轮廓重建任务在运行"}

    job.update({
        "running": True,
        "phase": "rebuilding",
        "startedAt": _now_iso(),
        "finishedAt": None,
        "error": None,
        "result": None,
    })
    _task = asyncio.create_task(_watch_rebuild(builder))
    return True, 200, {"success": True, "data": {"message": "轮廓重建已启动"}}
