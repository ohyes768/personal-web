"""valuation 路由集成测试（TestClient + 假 Hermes，不真连）。

覆盖：analyze 受理/503/400/422、GET /valuation、apply 成功/陈旧 409/非 ready 400/未收藏 404、
alerts/enabled 暂停恢复、失败与未应用不覆盖旧监控。
"""
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.models import DividendStock, StockListResponse
from src.services.favorites_service import FavoritesService
from src.services.valuation_service import ValuationService
from src.services.refresh_jobs import RefreshJobManager


def stock(**updates):
    fields = dict(code="000001", name="样本", exchange="深市主板", avg_yield_3y=4.2)
    fields.update(updates)
    return DividendStock(**fields)


def fake_report(code, name, status="ready", *, skill_version="1.0.0"):
    body = {
        "schema_version": "1.0.0", "skill_version": skill_version,
        "code": code, "name": name, "currency": "CNY", "as_of": "2026-11-11",
        "status": status, "levels": None, "valuation": None,
        "evidence": [{"id": "e1", "title": "年报摘要", "kind": "official",
                      "origin": "inline:2026-11-11:年报", "locator": "第二节", "period": "2025 年度",
                      "published_at": "2026-03-30", "accessed_at": "2026-11-11", "verification": "reused"}],
        "data_gaps": [], "confidence": {"level": "medium", "reason": "上游复用"},
        "risks": [], "invalidation_conditions": [],
        "summary": "有依据" if status == "ready" else "材料不足",
        "analysis": {"business": "b", "normalization": "n", "dividend": "d",
                     "valuation": "v", "risk": "r"},
        "report_md": "# 四挡位估值",
    }
    if status == "ready":
        body["levels"] = {
            "heavy_position": {"price": 10.0, "pe": 5.1, "pb": 0.7},
            "add_position": {"price": 12.0, "pe": 6.1, "pb": 0.8},
            "reduce_position": {"price": 15.0, "pe": 7.6, "pb": 1.0},
            "full_exit": {"price": 19.0, "pe": 9.7, "pb": 1.3},
        }
        body["valuation"] = {"primary_method": "pe_multiple", "anchor": "a"}
    return json.dumps(body, ensure_ascii=False)


@pytest.fixture
def client(monkeypatch, tmp_path):
    service = ValuationService(tmp_path / "valuation_reports.json")
    routes.set_valuation_service(service)
    manager = RefreshJobManager(tmp_path / "jobs")
    routes.set_refresh_jobs(manager)
    favorites = FavoritesService(tmp_path / "favorites.json")
    monkeypatch.setattr(routes, "favorites_service", favorites)
    monkeypatch.setattr(routes, "m120_service", None)
    monkeypatch.setattr(routes, "pe_service", None)
    favorites.add("000001")
    favorites.add("600000")
    favorites.update_alerts("600000", {"enabled": True, "updated_at": "2026-01-01T00:00:00",
                                       "levels": {"heavy_position": {"price": 9.0}}})

    async def load(**kwargs):
        items = [stock(), stock(code="600000", name="旧监控"), stock(code="600519", name="新股")]
        return StockListResponse(total=3, items=items, last_updated="2026-11-11")
    monkeypatch.setattr(routes, "get_stocks", load)
    monkeypatch.setattr(routes, "find_latest_aux_file", lambda *args: None)
    app = FastAPI()
    app.include_router(routes.router)
    yield TestClient(app), manager, favorites, service
    routes.set_valuation_service(None)


def wait_job(manager, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job and job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("job 未在超时内完成")


def configure_hermes(monkeypatch, version="1.0.0", status="ready"):
    monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
    monkeypatch.setenv("HERMES_API_KEY", "secret")
    monkeypatch.setenv("HERMES_VALUATION_SKILL_VERSION", version)
    monkeypatch.setattr(routes, "submit_run", lambda cfg, prompt, key: key)
    monkeypatch.setattr(routes, "poll_run",
                        lambda cfg, run_id: fake_report(run_id.split("-")[1], "样本", status=status))
    # _watch 路径用的单次查询/停止也要打桩
    monkeypatch.setattr(routes, "get_run",
                        lambda cfg, run_id: {"status": "completed",
                                             "output": fake_report(run_id.split("-")[1], "样本", status=status)})
    monkeypatch.setattr(routes, "stop_run", lambda cfg, run_id: "cancelled")


class TestAnalyze:
    def test_submit_202_and_persists(self, client, monkeypatch):
        test_client, manager, _, _ = client
        configure_hermes(monkeypatch)
        response = test_client.post("/valuation/analyze", json={"codes": ["000001"]})
        assert response.status_code == 202
        job = response.json()
        assert job["kind"] == "valuation"
        final = wait_job(manager, job["job_id"])
        assert final["status"] == "succeeded"

        reports = test_client.get("/valuation").json()
        assert reports["total"] == 1
        assert reports["reports"]["000001"]["status"] == "ready"
        assert reports["reports"]["000001"]["levels"]["heavy_position"]["price"] == 10.0
        assert reports["hermes_configured"] is True
        assert reports["current_skill_version"] == "1.0.0"
        assert reports["per_code"]["000001"]["state"] == "completed"

        job_view = test_client.get(f"/valuation/jobs/{job['job_id']}").json()
        assert job_view["per_code"]["000001"]["state"] == "completed"

    def test_unconfigured_returns_503(self, client, monkeypatch):
        test_client, _, _, _ = client
        monkeypatch.delenv("HERMES_BASE_URL", raising=False)
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        response = test_client.post("/valuation/analyze", json={"codes": ["000001"]})
        assert response.status_code == 503

    def test_code_not_in_pool_400(self, client, monkeypatch):
        test_client, _, _, _ = client
        configure_hermes(monkeypatch)
        response = test_client.post("/valuation/analyze", json={"codes": ["999999"]})
        assert response.status_code == 400
        assert "不在采集池" in response.json()["detail"]

    def test_empty_codes_422(self, client, monkeypatch):
        test_client, _, _, _ = client
        configure_hermes(monkeypatch)
        response = test_client.post("/valuation/analyze", json={"codes": []})
        assert response.status_code == 422

    def test_job_of_other_kind_404(self, client):
        test_client, _, _, _ = client
        assert test_client.get("/valuation/jobs/nonexistent").status_code == 404


class TestApply:
    def _evaluate(self, test_client, code="000001"):
        accepted = test_client.post("/valuation/analyze", json={"codes": [code]})
        job_id = accepted.json()["job_id"]
        job = wait_job(_manager_of(test_client), job_id)
        assert job["status"] == "succeeded", job
        return test_client.get("/valuation").json()["reports"][code]["evaluated_at"]

    def test_apply_ready_report_enables_monitoring(self, client, monkeypatch):
        test_client, _, favorites, _ = client
        configure_hermes(monkeypatch)
        evaluated_at = self._evaluate(test_client)
        response = test_client.post("/valuation/000001/apply", json={"evaluated_at": evaluated_at})
        assert response.status_code == 200
        item = next(it for it in response.json()["items"] if it["code"] == "000001")
        assert item["alerts"]["enabled"] is True
        assert item["alerts"]["levels"]["heavy_position"]["price"] == 10.0
        assert item["alerts"]["levels"]["full_exit"]["price"] == 19.0

    def test_apply_stale_report_conflicts(self, client, monkeypatch):
        test_client, _, _, _ = client
        configure_hermes(monkeypatch)
        first = self._evaluate(test_client)
        # 重评产生新报告
        configure_hermes(monkeypatch)
        accepted = test_client.post("/valuation/analyze", json={"codes": ["000001"]})
        wait_job(_manager_of(test_client), accepted.json()["job_id"])
        response = test_client.post("/valuation/000001/apply", json={"evaluated_at": first})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["status"] == "ready"
        assert detail["evaluated_at"] != first

    def test_apply_non_ready_rejected(self, client, monkeypatch):
        test_client, _, _, _ = client
        configure_hermes(monkeypatch, status="insufficient_data")
        evaluated_at = self._evaluate(test_client)
        response = test_client.post("/valuation/000001/apply", json={"evaluated_at": evaluated_at})
        assert response.status_code == 400
        assert "insufficient_data" in response.json()["detail"]

    def test_apply_without_report_404(self, client):
        test_client, _, _, _ = client
        response = test_client.post("/valuation/000001/apply", json={"evaluated_at": "2026-01-01T00:00:00"})
        assert response.status_code == 404

    def test_apply_not_favorited_404(self, client, monkeypatch):
        test_client, _, _, _ = client
        configure_hermes(monkeypatch)
        accepted = test_client.post("/valuation/analyze", json={"codes": ["600519"]})
        wait_job(_manager_of(test_client), accepted.json()["job_id"])
        reports = test_client.get("/valuation").json()["reports"]
        response = test_client.post("/valuation/600519/apply",
                                    json={"evaluated_at": reports["600519"]["evaluated_at"]})
        assert response.status_code == 404


class TestAlertsEnabled:
    def test_pause_keeps_levels(self, client):
        test_client, _, _, _ = client
        response = test_client.put("/favorites/600000/alerts/enabled", json={"enabled": False})
        assert response.status_code == 200
        item = next(it for it in response.json()["items"] if it["code"] == "600000")
        assert item["alerts"]["enabled"] is False
        assert item["alerts"]["levels"]["heavy_position"]["price"] == 9.0

    def test_resume(self, client):
        test_client, _, _, _ = client
        assert test_client.put("/favorites/600000/alerts/enabled", json={"enabled": False}).status_code == 200
        response = test_client.put("/favorites/600000/alerts/enabled", json={"enabled": True})
        item = next(it for it in response.json()["items"] if it["code"] == "600000")
        assert item["alerts"]["enabled"] is True

    def test_no_alerts_400(self, client):
        test_client, _, _, _ = client
        response = test_client.put("/favorites/000001/alerts/enabled", json={"enabled": False})
        assert response.status_code == 400

    def test_not_favorited_404(self, client):
        test_client, _, _, _ = client
        response = test_client.put("/favorites/999999/alerts/enabled", json={"enabled": False})
        assert response.status_code == 404


class TestOldMonitorPreserved:
    def test_failed_evaluation_never_touches_alerts(self, client, monkeypatch):
        test_client, _, favorites, _ = client
        before = favorites.get_all()["items"]
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642")
        monkeypatch.setenv("HERMES_API_KEY", "secret")
        monkeypatch.setenv("HERMES_VALUATION_SKILL_VERSION", "1.0.0")
        monkeypatch.setattr(routes, "submit_run", lambda cfg, prompt, key: key)
        monkeypatch.setattr(routes, "poll_run",
                            lambda cfg, run_id: (_ for _ in ()).throw(Exception("run 失败")))
        monkeypatch.setattr(routes, "get_run",
                            lambda cfg, run_id: {"status": "failed", "output": ""})
        monkeypatch.setattr(routes, "stop_run", lambda cfg, run_id: "cancelled")
        accepted = test_client.post("/valuation/analyze", json={"codes": ["600000"]})
        wait_job(_manager_of(test_client), accepted.json()["job_id"])
        after = favorites.get_all()["items"]
        assert before == after
        # 报告未落盘
        assert test_client.get("/valuation").json()["total"] == 0


def _manager_of(test_client):
    # job 轮询需要 manager；从 routes 全局拿（fixture 已设置）
    return routes.refresh_jobs


class TestQueueRoutes:
    """估值队列取消/调序路由：与 /quality/queue/* 同构。"""

    def _submit_three(self, test_client):
        accepted = test_client.post("/valuation/analyze", json={"codes": ["000001", "600000", "600519"]})
        assert accepted.status_code == 202
        return accepted.json()

    def _wait_state(self, service, code, state, timeout=5.0):
        import time as time_mod
        deadline = time_mod.monotonic() + timeout
        while time_mod.monotonic() < deadline:
            item = service.get_per_code().get(code) or {}
            if item.get("state") == state:
                return item
            time_mod.sleep(0.02)
        raise AssertionError(f"{code} 未在超时内进入 {state}")

    def test_cancel_and_move_routes(self, client, monkeypatch):
        test_client, manager, _, service = client
        configure_hermes(monkeypatch)
        # watch 路径打桩：release 前 get_run 一直 running；poll 间隔归零避免 30s 等待
        monkeypatch.setenv("HERMES_POLL_INTERVAL", "0")
        import threading
        release = threading.Event()
        monkeypatch.setattr(routes, "get_run",
                            lambda cfg, run_id: {"status": "running" if not release.is_set() else "completed",
                                                 "output": "" if not release.is_set()
                                                 else fake_report(run_id.split("-")[1], "样本")})
        job = self._submit_three(test_client)
        self._wait_state(service, "000001", "running")
        queued = service.get_per_code()
        assert [queued["600000"]["position"], queued["600519"]["position"]] == [1, 2]

        # 调序
        moved = test_client.post(f"/valuation/queue/{queued['600519']['item_id']}/move",
                                 json={"action": "front"})
        assert moved.status_code == 200
        assert moved.json()["per_code"]["600519"]["position"] == 1

        # 取消等待项
        cancelled = test_client.post(f"/valuation/queue/{queued['600000']['item_id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["per_code"]["600000"]["state"] == "cancelled"

        # 坏动作 422，过期身份 409
        assert test_client.post(f"/valuation/queue/{queued['600519']['item_id']}/move",
                                json={"action": "sideways"}).status_code == 422
        assert test_client.post(f"/valuation/queue/{queued['600000']['item_id']}/move",
                                json={"action": "front"}).status_code == 409

        release.set()
        deadline = 0
        while manager.get(job["job_id"])["status"] in ("queued", "running") and deadline < 100:
            import time as time_mod
            time_mod.sleep(0.05)
            deadline += 1
        final = manager.get(job["job_id"])
        assert final["status"] == "succeeded"
        assert final.get("cancelled") == 1
        reports = test_client.get("/valuation").json()["reports"]
        assert "600000" not in reports
        assert set(reports) == {"000001", "600519"}

    def test_cancel_unknown_item_409(self, client, monkeypatch):
        test_client, _, _, _ = client
        configure_hermes(monkeypatch)
        response = test_client.post("/valuation/queue/nonexistent/cancel")
        assert response.status_code == 409
