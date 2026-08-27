"""SchedulerManager._run_job_wrapper 单元测试

核心验证：组任务 result 里的 items（数据源子明细）透传到 history record 落盘。
不 start() 真实 scheduler，仅构造 manager 后手动填 jobs_meta。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.scheduler.manager import SchedulerManager


def make_manager(tmp_path: Path) -> SchedulerManager:
    """构造未 start 的 manager（config_path 不存在也不影响 _run_job_wrapper）"""
    mgr = SchedulerManager(
        port=18094,
        config_path=tmp_path / "scheduler.json",
        history_path=tmp_path / "history.jsonl",
    )
    mgr.jobs_meta = {
        "a_share_daily": {
            "id": "a_share_daily",
            "name": "A 股数据日度组",
            "target": "run_group",
            "cron": "10 16 * * 1-5",
            "check_trading_day": False,
            "targets": ["/update/vix", "/update/tga"],
        }
    }
    return mgr


@pytest.mark.unit
def test_run_job_wrapper_persists_items(tmp_path):
    """target 返回带 items → history record 含 items（页面子明细数据源）"""
    mgr = make_manager(tmp_path)
    items = [
        {"path": "/update/vix", "status": "success", "count": None, "ms": 120, "error": None},
        {"path": "/update/tga", "status": "failed", "count": None, "ms": 300, "error": "HTTP 500"},
    ]

    async def fake_run_group(ctx, job_id):
        return {
            "status": "partial",
            "count": 1,
            "items": items,
            "start": "2026-08-26T16:10:00",
            "end": "2026-08-26T16:10:01",
        }

    with patch("src.scheduler.manager.JOB_TARGETS", {"run_group": fake_run_group}):
        asyncio.run(mgr._run_job_wrapper("a_share_daily"))

    # 直接读 JSONL 文件断言 items 落盘
    lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["job_id"] == "a_share_daily"
    assert record["status"] == "partial"
    assert record["count"] == 1
    assert record["items"] == items
    # manager API 读回同样包含 items
    runs = mgr.get_job_runs("a_share_daily")
    assert runs[0]["items"] == items


@pytest.mark.unit
def test_run_job_wrapper_records_unhandled_exception(tmp_path):
    """target 抛异常 → 落 failed 记录（unhandled 前缀），不向上抛"""
    mgr = make_manager(tmp_path)

    async def boom(ctx, job_id):
        raise RuntimeError("akshare 挂了")

    with patch("src.scheduler.manager.JOB_TARGETS", {"run_group": boom}):
        asyncio.run(mgr._run_job_wrapper("a_share_daily"))

    runs = mgr.get_job_runs("a_share_daily")
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"].startswith("unhandled:")


@pytest.mark.unit
def test_run_job_wrapper_unknown_job_is_noop(tmp_path):
    """未知 job_id：不写历史、不抛异常"""
    mgr = make_manager(tmp_path)
    asyncio.run(mgr._run_job_wrapper("not_exist"))
    assert not (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip()
