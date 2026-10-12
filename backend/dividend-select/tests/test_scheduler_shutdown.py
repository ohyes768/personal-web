"""Lifecycle regression tests with a real APScheduler and isolated job targets."""

import asyncio
import json

import pytest
from apscheduler.schedulers.base import STATE_STOPPED

from src.scheduler.jobs import JOB_TARGETS
from src.scheduler.manager import SchedulerManager


@pytest.mark.parametrize("mode", ["idle", "drain", "timeout", "no_wait"])
def test_shutdown_stops_scheduler_and_handles_running_jobs(tmp_path, monkeypatch, mode):
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()
        cancelled = asyncio.Event()

        async def target(ctx, job_id):
            started.set()
            try:
                await release.wait()
                finished.set()
                return {"status": "success", "count": 1}
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def probe(self):
            pass

        monkeypatch.setitem(JOB_TARGETS, "shutdown_test", target)
        monkeypatch.setattr(SchedulerManager, "_delayed_self_port_probe", probe)
        config = tmp_path / "scheduler.json"
        config.write_text(json.dumps({"jobs": [{"id": "test", "target": "shutdown_test", "cron": "0 0 * * *"}]}))
        manager = SchedulerManager(8092, config, tmp_path / "runs.jsonl")
        manager.start({})
        scheduler = manager._scheduler
        try:
            if mode != "idle":
                await manager.trigger_now("test")
                await asyncio.wait_for(started.wait(), 1)
            closing = asyncio.create_task(manager.shutdown(wait=mode != "no_wait", timeout=0.03 if mode == "timeout" else 1))
            await asyncio.sleep(0)
            if mode == "drain":
                assert not closing.done(), "shutdown must wait for the running job"
                with pytest.raises(RuntimeError):
                    await manager.trigger_now("test")
                with pytest.raises(RuntimeError):
                    manager.set_enabled("test", True)
                await manager._run_job_wrapper("test")  # no new work during drain
                release.set()
            await asyncio.wait_for(closing, 1)
            assert scheduler.state == STATE_STOPPED
            assert manager._scheduler is None
            assert not manager._running_tasks
            if mode != "idle":
                assert not manager._run_locks["test"].locked()
            if mode == "drain":
                assert finished.is_set()
                assert not cancelled.is_set()
                assert manager.get_job_runs("test")[0]["status"] == "success"
            elif mode in ("timeout", "no_wait"):
                assert cancelled.is_set()
                assert not finished.is_set()
            await manager.shutdown()  # repeated shutdown is harmless
            manager.start({})
            assert not manager._closing
            await manager.shutdown()
            assert manager._scheduler is None
        finally:
            release.set()
            if scheduler.running:
                scheduler.shutdown(wait=False)
                await asyncio.sleep(0)

    asyncio.run(scenario())
