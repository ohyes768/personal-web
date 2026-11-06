"""scheduler 管理 API 路由测试：200/404/503 语义。

用 stub manager（不起真实调度线程，沿 task-web conftest 的 TestClient 手法），
只验证路由行为与错误语义，manager 逻辑由 test_scheduler_manager.py 覆盖。
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.scheduler.routes import router


class StubManager:
    """行为正确、可注入错误的 manager 桩。"""

    def __init__(self):
        self.jobs = [{"id": "process_pending", "name": "转写待处理视频", "enabled": True}]

    def list_jobs(self):
        return self.jobs

    def set_enabled(self, job_id: str, enabled: bool):
        if job_id not in {j["id"] for j in self.jobs}:
            raise KeyError(job_id)
        return {"id": job_id, "enabled": enabled}

    def trigger_now(self, job_id: str, trigger: str = "manual"):
        if job_id not in {j["id"] for j in self.jobs}:
            raise KeyError(job_id)
        return {"job_id": job_id, "triggered_at": "2026-11-06T10:00:00"}

    def get_job_runs(self, job_id: str, limit: int = 20):
        if job_id not in {j["id"] for j in self.jobs}:
            raise KeyError(job_id)
        return [{"job_id": job_id, "trigger": "manual", "status": "success", "count": 1}]


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    app.state.scheduler = StubManager()
    return TestClient(app)


def test_list_jobs_ok(client):
    resp = client.get("/api/scheduler/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jobs"][0]["id"] == "process_pending"


def test_patch_job_ok(client):
    resp = client.patch("/api/scheduler/jobs/process_pending", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_patch_job_not_found(client):
    resp = client.patch("/api/scheduler/jobs/nope", json={"enabled": True})
    assert resp.status_code == 404


def test_run_job_ok(client):
    resp = client.post("/api/scheduler/jobs/process_pending/run")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "process_pending"


def test_run_job_not_found(client):
    resp = client.post("/api/scheduler/jobs/nope/run")
    assert resp.status_code == 404


def test_get_runs_ok(client):
    resp = client.get("/api/scheduler/jobs/process_pending/runs?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_returned"] == 1
    assert body["runs"][0]["trigger"] == "manual"


def test_get_runs_limit_validated(client):
    resp = client.get("/api/scheduler/jobs/process_pending/runs?limit=500")
    assert resp.status_code == 422  # Query ge=1 le=200


def test_scheduler_not_initialized_returns_503():
    app = FastAPI()
    app.include_router(router)
    # app.state.scheduler 未设置 → 503
    client = TestClient(app)
    assert client.get("/api/scheduler/jobs").status_code == 503
    assert client.post("/api/scheduler/jobs/process_pending/run").status_code == 503


def test_runtime_error_maps_to_503():
    app = FastAPI()
    app.include_router(router)

    manager = StubManager()

    def boom(job_id, enabled):
        raise RuntimeError("scheduler 未启动")

    manager.set_enabled = boom
    app.state.scheduler = manager
    client = TestClient(app)
    resp = client.patch("/api/scheduler/jobs/process_pending", json={"enabled": True})
    assert resp.status_code == 503
    assert "scheduler 未启动" in resp.json()["detail"]
