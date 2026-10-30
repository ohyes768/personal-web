"""quality 路由集成测试（TestClient + 假 Hermes，不真连）。"""
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.models import DividendStock, StockListResponse
from src.services.hermes_client import HermesRunCancelled, HermesRunFailed
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

    def fake_get(cfg, run_id):
        try:
            output = routes.poll_run(cfg, run_id)
        except HermesRunCancelled:
            return {"status": "cancelled"}
        except HermesRunFailed as exc:
            return {"status": "failed", "error": str(exc)}
        return {"status": "completed", "output": output}

    monkeypatch.setattr(routes, "get_run", fake_get)
    monkeypatch.setattr(routes, "stop_run", lambda cfg, run_id: "stopping")
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
    def test_current_and_reported_skill_versions_are_exposed(self, client, monkeypatch):
        test_client, manager = client
        monkeypatch.setenv('HERMES_BASE_URL', 'http://nas:8642')
        monkeypatch.setenv('HERMES_API_KEY', 'secret')
        monkeypatch.setenv('HERMES_QUALITY_SKILL_VERSION', '4.3.0')
        monkeypatch.setattr(routes, 'submit_run', lambda *args: 'versioned-run')
        output = json.loads(fake_output('000001', '样本'))
        output['skill_version'] = '4.3.0'
        monkeypatch.setattr(routes, 'poll_run', lambda *args: json.dumps(output))
        accepted = test_client.post('/quality/analyze', json={'codes': ['000001']})
        assert accepted.status_code == 202
        assert wait_job(manager, accepted.json()['job_id'])['status'] == 'succeeded'
        response = test_client.get('/quality')
        assert response.json()['current_skill_version'] == '4.3.0'
        assert response.json()['scores']['000001']['skill_version'] == '4.3.0'

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
            assert gate.wait(120)
            if "600519" in run_id:
                return fake_output("600519", "新股")
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


class TestQueueActions:
    def _configure(self, monkeypatch, poll):
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        monkeypatch.setenv("HERMES_MAX_CONCURRENT", "1")
        monkeypatch.setattr(routes, "submit_run", lambda cfg, prompt, key: key)
        monkeypatch.setattr(routes, "poll_run", poll)

    def test_cancel_waiting_is_idempotent_and_move_reports_conflict(self, client, monkeypatch):
        import threading
        test_client, manager = client
        gate = threading.Event()

        async def load(**kwargs):
            items = [stock(), stock(code="600519", name="乙"), stock(code="000002", name="丙")]
            return StockListResponse(total=3, items=items, last_updated="2026-10-23")

        monkeypatch.setattr(routes, "get_stocks", load)

        def poll(cfg, run_id):
            if "000001" in run_id:
                gate.wait(5)
            name = "乙" if "600519" in run_id else "丙" if "000002" in run_id else "样本"
            code = "600519" if "600519" in run_id else "000002" if "000002" in run_id else "000001"
            return fake_output(code, name)

        self._configure(monkeypatch, poll)
        accepted = test_client.post("/quality/analyze", json={"codes": ["000001", "600519", "000002"]})
        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]

        def queued_ready():
            live = test_client.get(f"/quality/jobs/{job_id}").json()["per_code"]
            return live["000001"]["state"] == "running" and live["000002"]["state"] == "queued"

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not queued_ready():
            time.sleep(0.02)
        live = test_client.get(f"/quality/jobs/{job_id}").json()["per_code"]
        assert live["600519"]["position"] == 1
        moved = test_client.post(f"/quality/queue/{live['000002']['item_id']}/move", json={"action": "front"})
        assert moved.status_code == 200
        assert moved.json()["per_code"]["000002"]["position"] == 1
        assert moved.json()["per_code"]["600519"]["position"] == 2
        boundary = test_client.post(f"/quality/queue/{live['000002']['item_id']}/move", json={"action": "up"})
        assert boundary.status_code == 409
        assert "队首" in boundary.json()["detail"]["message"]
        running_move = test_client.post(f"/quality/queue/{live['000001']['item_id']}/move", json={"action": "down"})
        assert running_move.status_code == 409
        assert running_move.json()["detail"]["per_code"]["000001"]["state"] == "running"
        waiting_id = moved.json()["per_code"]["600519"]["item_id"]
        cancelled = test_client.post(f"/quality/queue/{waiting_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["per_code"]["600519"]["state"] == "cancelled"
        duplicate = test_client.post(f"/quality/queue/{waiting_id}/cancel")
        assert duplicate.status_code == 200
        assert manager.get(job_id)["cancelled"] == 1
        stale = test_client.post("/quality/analyze", json={"codes": ["600519"]})
        assert stale.status_code == 202 and stale.json()["reused"] is True
        new_id = stale.json()["per_code"]["600519"]["item_id"]
        assert new_id != waiting_id
        conflict = test_client.post(f"/quality/queue/{waiting_id}/cancel")
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["per_code"]["600519"]["item_id"] == new_id
        assert test_client.post("/quality/queue/missing/cancel").status_code == 409
        assert test_client.post(f"/quality/queue/{new_id}/move", json={"action": "sideways"}).status_code == 422
        gate.set()
        wait_job(manager, job_id)
