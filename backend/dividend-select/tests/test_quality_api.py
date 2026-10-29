"""quality 路由集成测试（TestClient + 假 Hermes，不真连）。"""
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.models import DividendStock, StockListResponse
from src.services.quality_service import QualityService
from src.services.refresh_jobs import RefreshJobManager


def stock(**updates):
    fields = dict(code="000001", name="样本", exchange="深市主板", avg_yield_3y=4.2)
    fields.update(updates)
    return DividendStock(**fields)


def fake_output(code, name):
    weighted = round(4 * 0.25 + 5 * 0.25 + 3 * 0.20 + 3 * 0.15 + 5 * 0.15, 2)
    return json.dumps({
        "code": code, "name": name,
        "dimensions": {"business": 4, "moat": 5, "industry": 3, "management": 3, "financial": 5},
        "weighted_score": weighted, "stars": 4, "boundary": None,
        "summary": "质量尚可", "risks": [], "watch_points": [],
        "report_md": "# 基本面评级",
    }, ensure_ascii=False)


@pytest.fixture
def client(monkeypatch, tmp_path):
    service = QualityService(tmp_path / "quality_scores.json")
    routes.set_quality_service(service)
    manager = RefreshJobManager(tmp_path / "jobs")
    routes.set_refresh_jobs(manager)
    async def load(**kwargs):
        items = [stock(), stock(code="600519", name="新股")]
        return StockListResponse(total=2, items=items, last_updated="2026-10-23")
    monkeypatch.setattr(routes, "get_stocks", load)
    monkeypatch.setattr(routes, "find_latest_aux_file", lambda *args: None)
    app = FastAPI()
    app.include_router(routes.router)
    yield TestClient(app), manager
    routes.set_quality_service(None)


def wait_job(manager, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job and job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("job 未在超时内完成")


class TestAnalyze:
    def test_unconfigured_returns_503(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.delenv("HERMES_BASE_URL", raising=False)
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        response = test_client.post("/quality/analyze", json={"codes": ["000001"]})
        assert response.status_code == 503
        assert "Hermes" in response.json()["detail"]

    def test_submit_returns_202_and_persists(self, client, monkeypatch):
        test_client, manager = client
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        monkeypatch.setattr(routes, "submit_run", lambda cfg, prompt, key: "run-1")
        monkeypatch.setattr(routes, "poll_run", lambda cfg, run_id: fake_output("000001", "样本"))

        response = test_client.post("/quality/analyze", json={"codes": ["000001"]})
        assert response.status_code == 202
        job = response.json()
        assert job["kind"] == "quality"
        assert job["codes"] == ["000001"]
        final = wait_job(manager, job["job_id"])
        assert final["status"] == "succeeded"

        scores = test_client.get("/quality").json()
        assert scores["total"] == 1
        assert scores["scores"]["000001"]["stars"] == 4
        assert scores["scores"]["000001"]["report_md"] == "# 基本面评级"
        assert scores["per_code"]["000001"]["state"] == "completed"

        job_view = test_client.get(f"/quality/jobs/{job['job_id']}").json()
        assert job_view["per_code"]["000001"]["state"] == "completed"

    def test_active_job_reused(self, client, monkeypatch):
        import threading
        test_client, manager = client
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        gate = threading.Event()

        def slow_poll(cfg, run_id):
            gate.wait(120)
            return fake_output("000001", "样本")

        monkeypatch.setattr(routes, "submit_run", lambda cfg, prompt, key: "run-1")
        monkeypatch.setattr(routes, "poll_run", slow_poll)
        first = test_client.post("/quality/analyze", json={"codes": ["000001"]})
        assert first.status_code == 202
        second = test_client.post("/quality/analyze", json={"codes": ["000001"]})
        assert second.status_code == 202
        assert second.json()["job_id"] == first.json()["job_id"]
        assert second.json()["reused"] is True
        gate.set()
        wait_job(manager, first.json()["job_id"])

    def test_append_new_code_while_running(self, client, monkeypatch):
        import threading
        test_client, manager = client
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        gate = threading.Event()

        def slow_poll(cfg, run_id):
            if "600519" in run_id:
                return fake_output("600519", "新股")
            gate.wait(120)
            return fake_output("000001", "样本")

        monkeypatch.setattr(routes, "submit_run", lambda cfg, prompt, key: f"run-{key}")
        monkeypatch.setattr(routes, "poll_run", slow_poll)
        first = test_client.post("/quality/analyze", json={"codes": ["000001"]})
        assert first.status_code == 202
        second = test_client.post("/quality/analyze", json={"codes": ["600519"]})
        assert second.status_code == 202
        assert second.json()["job_id"] == first.json()["job_id"]
        assert second.json()["reused"] is True
        assert second.json()["codes"] == ["000001", "600519"]
        live = test_client.get(f"/quality/jobs/{first.json()['job_id']}").json()
        # 并发余量足够时追加项可能立即开跑，只要进入受理即可
        assert live["per_code"]["600519"]["state"] in ("queued", "running")
        gate.set()
        wait_job(manager, first.json()["job_id"])
        assert test_client.get("/quality").json()["total"] == 2
        final = test_client.get(f"/quality/jobs/{first.json()['job_id']}").json()
        assert final["per_code"]["600519"]["state"] == "completed"

    def test_missing_code_returns_400(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        response = test_client.post("/quality/analyze", json={"codes": ["999999"]})
        assert response.status_code == 400
        assert "999999" in response.json()["detail"]

    def test_invalid_code_returns_422(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        assert test_client.post("/quality/analyze", json={"codes": ["ABC"]}).status_code == 422
        assert test_client.post("/quality/analyze", json={"codes": []}).status_code == 422


class TestJobQuery:
    def test_unknown_job_returns_404(self, client):
        test_client, _ = client
        assert test_client.get("/quality/jobs/nonexistent").status_code == 404

    def test_non_quality_job_returns_404(self, client, monkeypatch, tmp_path):
        test_client, manager = client
        job = manager.submit("m120", ["000001"], lambda progress: progress("000001", True))
        assert test_client.get(f"/quality/jobs/{job['job_id']}").status_code == 404

    def test_job_query_after_completion(self, client, monkeypatch):
        test_client, manager = client
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        monkeypatch.setattr(routes, "submit_run", lambda cfg, prompt, key: "run-1")
        monkeypatch.setattr(routes, "poll_run", lambda cfg, run_id: fake_output("000001", "样本"))
        submitted = test_client.post("/quality/analyze", json={"codes": ["000001"]}).json()
        wait_job(manager, submitted["job_id"])
        job = test_client.get(f"/quality/jobs/{submitted['job_id']}").json()
        assert job["status"] == "succeeded"
        assert (job["processed"], job["succeeded"]) == (1, 1)


class TestScores:
    def test_empty_scores(self, client):
        test_client, _ = client
        body = test_client.get("/quality").json()
        assert body["total"] == 0
        assert body["scores"] == {}
        assert isinstance(body["hermes_configured"], bool)

    def test_hermes_configured_reflects_env(self, client, monkeypatch):
        test_client, _ = client
        monkeypatch.delenv("HERMES_BASE_URL", raising=False)
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        assert test_client.get("/quality").json()["hermes_configured"] is False
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        assert test_client.get("/quality").json()["hermes_configured"] is True

    def test_service_missing_returns_500(self, monkeypatch, tmp_path):
        routes.set_quality_service(None)
        app = FastAPI()
        app.include_router(routes.router)
        assert TestClient(app).get("/quality").status_code == 500
