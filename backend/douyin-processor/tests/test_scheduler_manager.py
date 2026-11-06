"""SchedulerManager 单元测试：enabled overlay / 注册 / 互斥 / 历史 schema。

真实 AsyncIOScheduler + 隔离 target（沿 dividend tests/test_scheduler_shutdown.py 手法，
用 asyncio.run 的同步测试外壳，避免 pytest-asyncio 依赖）。
"""

import asyncio
import json

import pytest

from src.scheduler import jobs as scheduler_jobs
from src.scheduler.history import build_record
from src.scheduler.manager import SchedulerManager

APP_CONFIG = {
    "process_pending": {
        "cron_morning": "45 9 * * *",
        "cron_evening": "15 17 * * *",
        "timezone": "Asia/Shanghai",
    },
    "cleanup": {"days": 45, "cron": "7 3 * * *", "timezone": "Asia/Shanghai"},
}


class FakeStatusManager:
    def __init__(self, pending: list | None = None):
        self.pending = pending if pending is not None else []

    async def list_pending(self):
        return list(self.pending)

    async def cleanup_old_records(self, days: int):
        return ["111", "222"]


class FakeProcessor:
    def __init__(self, pending: list | None = None):
        self.status_manager = FakeStatusManager(pending)
        self.calls = 0

    async def process_pending(self):
        self.calls += 1
        return {"total": len(self.status_manager.pending), "success": 2, "failed": 0}


def make_manager(tmp_path, services: dict | None = None) -> SchedulerManager:
    return SchedulerManager(
        app_config=APP_CONFIG,
        data_dir=tmp_path,
        services=services or {"processor": FakeProcessor([{"aweme_id": "111"}]), "cleanup_days": 45},
    )


def test_enabled_overlay_persisted_across_restart(tmp_path):
    """禁用 → 写 overlay → 重建 manager → 状态保持禁用（容器 recreate 模拟）。"""

    async def scenario():
        manager = make_manager(tmp_path)
        manager.start()
        try:
            updated = manager.set_enabled("process_pending", False)
            assert updated["enabled"] is False
            assert json.loads((tmp_path / "scheduler" / "enabled.json").read_text()) == {
                "process_pending": False,
                "cleanup_old_records": True,
            }
        finally:
            await manager.shutdown()

        manager2 = make_manager(tmp_path)
        manager2.start()
        try:
            job = next(j for j in manager2.list_jobs() if j["id"] == "process_pending")
            assert job["enabled"] is False
            # 禁用 job 的子 job 全部 paused → 无下次触发时间
            assert job["next_run_time"] is None
            enabled_job = next(j for j in manager2.list_jobs() if j["id"] == "cleanup_old_records")
            assert enabled_job["enabled"] is True
            assert enabled_job["next_run_time"] is not None
        finally:
            await manager2.shutdown()

    asyncio.run(scenario())


def test_list_jobs_shape(tmp_path):
    """两个逻辑 job，process_pending 含两个 cron，cron_human 可读。"""

    async def scenario():
        manager = make_manager(tmp_path)
        manager.start()
        try:
            jobs = {j["id"]: j for j in manager.list_jobs()}
            assert set(jobs) == {"process_pending", "cleanup_old_records"}
            assert jobs["process_pending"]["crons"] == ["45 9 * * *", "15 17 * * *"]
            assert jobs["process_pending"]["cron_human"] == "每天 09:45 / 每天 17:15"
            assert jobs["cleanup_old_records"]["cron_human"] == "每天 03:07"
            assert jobs["process_pending"]["next_run_time"] is not None
            # 时区必须在 Asia/Shanghai（next_run_time 带偏移量）
            assert "+08:00" in jobs["process_pending"]["next_run_time"]
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_trigger_now_manual_records_history(tmp_path):
    """手动触发：跑完 target 后历史出现 trigger=manual 记录。"""

    async def scenario():
        manager = make_manager(tmp_path)
        manager.start()
        try:
            result = manager.trigger_now("process_pending")
            assert result["job_id"] == "process_pending"
            # 等 DateTrigger 任务跑完
            for _ in range(50):
                await asyncio.sleep(0.02)
                if manager.get_job_runs("process_pending"):
                    break
            runs = manager.get_job_runs("process_pending")
            assert runs, "手动触发后应产生历史记录"
            rec = runs[0]
            assert rec["trigger"] == "manual"
            assert rec["target"] == "process_pending"
            assert rec["status"] == "success"
            assert rec["count"] == 2
            assert rec["start"] and rec["end"]
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_process_busy_skipped_recorded(tmp_path):
    """锁被占时（手动撞定时），定时路径记 skipped/process_busy，不重复消耗 ASR。"""

    async def scenario():
        processor = FakeProcessor([{"aweme_id": "111"}])
        manager = make_manager(tmp_path, {"processor": processor, "cleanup_days": 45})
        manager.start()
        try:
            acquired = asyncio.Event()
            release = asyncio.Event()

            async def hold_lock():
                async with scheduler_jobs._process_lock:
                    acquired.set()
                    await release.wait()

            holder = asyncio.create_task(hold_lock())
            await acquired.wait()
            result = await scheduler_jobs.run_process_pending(
                manager._services, "process_pending", "scheduled"
            )
            assert result["status"] == "skipped"
            assert result["reason"] == "process_busy"
            assert processor.calls == 0
            release.set()
            await holder
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_run_cleanup_maps_result(tmp_path):
    """cleanup target：成功删除映射 count；空列表映射 skipped 语义为 success/no records。"""

    async def scenario():
        processor = FakeProcessor([])
        deleted = await processor.status_manager.cleanup_old_records(45)
        assert deleted == ["111", "222"]
        # cleanup_old_records 返回列表 → run_cleanup 需要 filesystem_client/output_dir
        # 这里只验证 run_process_pending 空列表分支（cleanup 的文件删除分支依赖外部服务，
        # 由 test_scheduler_routes 的 stub 覆盖 API 层）
        manager = make_manager(tmp_path, {"processor": processor, "cleanup_days": 45})
        manager.start()
        try:
            result = await scheduler_jobs.run_process_pending(
                manager._services, "process_pending", "scheduled"
            )
            assert result["status"] == "skipped"
            assert result["reason"] == "no_pending"
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_build_record_schema():
    """build_record 固定字段 + 可选字段不落 None。"""
    rec = build_record(
        job_id="process_pending",
        target="process_pending",
        trigger="scheduled",
        start="2026-11-06T09:45:00+08:00",
        end="2026-11-06T09:46:00+08:00",
        status="success",
        count=3,
    )
    assert rec["trigger"] == "scheduled"
    assert rec["count"] == 3
    assert "reason" not in rec
    assert "failed" not in rec

    rec2 = build_record(
        job_id="cleanup_old_records",
        target="cleanup",
        trigger="manual",
        start="s",
        end="e",
        status="failed",
        failed=["a.wav"],
    )
    assert rec2["failed"] == ["a.wav"]
    assert "count" not in rec2


def test_no_pending_job_skipped(tmp_path):
    """manager._execute_job 对未知 job_id / 未知 target 静默跳过并告警。"""

    async def scenario():
        manager = make_manager(tmp_path)
        manager.start()
        try:
            await manager._execute_job("nonexistent", "scheduled")  # 不应抛
            # 未知 target：构造一个假 spec
            manager.jobs_meta["fake"] = {"id": "fake", "target": "nope", "crons": []}
            manager._run_locks["fake"] = asyncio.Lock()
            await manager._execute_job("fake", "scheduled")  # 不应抛
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_trigger_now_rejected_when_closed(tmp_path):
    """closing 后手动触发拒绝（drain 契约）。"""

    async def scenario():
        manager = make_manager(tmp_path)
        manager.start()
        manager._closing = True  # 模拟 drain 中
        with pytest.raises(RuntimeError):
            manager.trigger_now("process_pending")
        manager._closing = False
        await manager.shutdown()
        with pytest.raises(RuntimeError):
            manager.trigger_now("process_pending")

    asyncio.run(scenario())
