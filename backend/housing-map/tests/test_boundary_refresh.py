import asyncio

from src.services import boundary_refresh


def test_boundary_rebuild_runs_only_the_injected_boundary_builder(monkeypatch):
    monkeypatch.setattr(boundary_refresh, "job", {
        "running": False,
        "phase": "idle",
        "startedAt": None,
        "finishedAt": None,
        "error": None,
        "result": None,
    })
    monkeypatch.setattr(boundary_refresh, "_task", None)

    async def run_job():
        ok, status, body = await boundary_refresh.start_rebuild(
            builder=lambda: {"matched": 10, "unmatched": 2, "total": 12}
        )
        assert ok is True
        assert status == 200
        assert body["success"] is True
        task = boundary_refresh._task
        assert task is not None
        await task

    asyncio.run(run_job())

    assert boundary_refresh.job["phase"] == "done"
    assert boundary_refresh.job["result"] == {"matched": 10, "unmatched": 2, "total": 12}
