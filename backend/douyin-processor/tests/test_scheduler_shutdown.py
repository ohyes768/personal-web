"""Lifecycle regression tests with a real APScheduler and isolated job targets.

沿 dividend tests/test_scheduler_shutdown.py 裁剪：idle stop / 执行中 drain /
closing 拒绝新工作 / 重复 shutdown 无害。
"""

import asyncio

import pytest
from apscheduler.schedulers.base import STATE_STOPPED

from src.scheduler.jobs import JOB_TARGETS
from src.scheduler.manager import SchedulerManager


@pytest.mark.parametrize("mode", ["idle", "drain"])
def test_shutdown_stops_scheduler_and_handles_running_jobs(tmp_path, monkeypatch, mode):
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()
        cancelled = asyncio.Event()

        async def target(services, job_id, trigger="scheduled"):
            started.set()
            try:
                await release.wait()
                finished.set()
                return {"status": "success", "count": 1}
            except asyncio.CancelledError:
                cancelled.set()
                raise

        monkeypatch.setitem(JOB_TARGETS, "shutdown_test", target)

        manager = SchedulerManager(
            app_config={
                "process_pending": {"cron_morning": "45 9 * * *", "cron_evening": "15 17 * * *", "timezone": "Asia/Shanghai"},
                "cleanup": {"cron": "7 3 * * *", "timezone": "Asia/Shanghai"},
            },
            data_dir=tmp_path,
            services={},
        )
        # 注入测试 job：绕过 app.yaml cron_map，直接写 jobs_meta 后注册
        manager.jobs_meta = {
            "process_pending": {
                "id": "process_pending",
                "name": "test",
                "target": "shutdown_test",
                "crons": ["45 9 * * *", "15 17 * * *"],
                "enabled": True,
            },
            "cleanup_old_records": {
                "id": "cleanup_old_records",
                "name": "cleanup",
                "target": "shutdown_test",
                "crons": ["7 3 * * *"],
                "enabled": True,
            },
        }
        manager._run_locks = {k: asyncio.Lock() for k in manager.jobs_meta}

        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler(
            timezone="Asia/Shanghai",
            job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 3600},
        )
        for job_id, spec in manager.jobs_meta.items():
            for i, cron in enumerate(spec["crons"]):
                scheduler.add_job(
                    manager._run_job_wrapper,
                    CronTrigger.from_crontab(cron, timezone="Asia/Shanghai"),
                    id=f"{job_id}#{i}",
                    args=[job_id],
                    replace_existing=True,
                )
        scheduler.start()
        manager._scheduler = scheduler

        try:
            if mode != "idle":
                manager.trigger_now("process_pending")
                await asyncio.wait_for(started.wait(), 1)
            closing = asyncio.create_task(manager.shutdown(wait=True, timeout=1))
            await asyncio.sleep(0)
            if mode == "drain":
                assert not closing.done(), "shutdown must wait for the running job"
                with pytest.raises(RuntimeError):
                    await manager.trigger_now("process_pending")
                with pytest.raises(RuntimeError):
                    manager.set_enabled("process_pending", True)
                await manager._run_job_wrapper("process_pending")  # no new work during drain
                release.set()
            await asyncio.wait_for(closing, 1)
            assert scheduler.state == STATE_STOPPED
            assert manager._scheduler is None
            assert not manager._running_tasks
            if mode != "idle":
                assert not manager._run_locks["process_pending"].locked()
            if mode == "drain":
                assert finished.is_set()
                assert not cancelled.is_set()
                assert manager.get_job_runs("process_pending")[0]["status"] == "success"
            await manager.shutdown()  # repeated shutdown is harmless
            assert manager._scheduler is None
        finally:
            release.set()
            if scheduler.running:
                scheduler.shutdown(wait=False)
                await asyncio.sleep(0)

    asyncio.run(scenario())
