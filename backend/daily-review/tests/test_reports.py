"""reports 列表/详情 + generate（mock DeepSeek）成功与失败路径测试。"""
import httpx
import pytest


@pytest.fixture()
def some_records(client, auth_headers):
    recs = [
        {
            "machine": "windows", "kind": "session", "project": "alpha",
            "external_id": "r1", "title": "会话A", "summary_text": "改了 routes",
            "started_at": "2026-11-27T09:00:00Z", "ended_at": "2026-11-27T10:00:00Z", "payload": {},
        },
        {
            "machine": "nas", "kind": "git_commit", "project": "alpha",
            "external_id": "abc123", "title": "fix: bug", "summary_text": "修 bug",
            "started_at": "2026-11-27T11:00:00Z", "ended_at": "", "payload": {},
        },
    ]
    client.post("/api/review/ingest/records", json={"records": recs}, headers=auth_headers)
    return recs


def _mock_deepseek(monkeypatch, fail=False):
    calls = []

    def fake_post(url, **kw):
        calls.append({"url": url, "kw": kw})
        if fail:
            resp = httpx.Response(500, request=httpx.Request("POST", url))
            resp.raise_for_status()
            return resp
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "# 日报\n\n今天做了两件事。"}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return calls


class TestGenerate:
    def test_no_api_key_returns_503(self, client, some_records):
        r = client.post("/api/review/reports/generate", json={"report_type": "daily"})
        assert r.status_code == 503
        assert "DEEPSEEK_API_KEY" in r.json()["detail"]

    def test_success_daily(self, client, some_records, monkeypatch):
        calls = _mock_deepseek(monkeypatch)
        r = client.post(
            "/api/review/reports/generate",
            json={"report_type": "daily", "period_start": "2026-11-27"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "done"
        assert data["period_start"] == "2026-11-27"
        assert data["period_end"] == "2026-11-27"
        assert data["record_count"] == 2
        assert calls[0]["url"].endswith("/chat/completions")
        body = calls[0]["kw"]["json"]
        assert body["model"] == "deepseek-chat"
        assert "会话A" in body["messages"][1]["content"]

        # 列表 + 详情
        lst = client.get("/api/review/reports", params={"type": "daily"}).json()["reports"]
        assert len(lst) == 1 and lst[0]["status"] == "done"
        assert "日报" in lst[0]["summary_first_paragraph"]
        detail = client.get(f"/api/review/reports/{data['id']}").json()
        assert detail["summary_md"].startswith("# 日报")
        assert len(detail["records"]) == 2
        assert detail["records"][0]["title"] == "会话A"

    def test_failure_lands_failed(self, client, some_records, monkeypatch):
        _mock_deepseek(monkeypatch, fail=True)
        r = client.post(
            "/api/review/reports/generate",
            json={"report_type": "daily", "period_start": "2026-11-27"},
        )
        assert r.status_code == 502
        lst = client.get("/api/review/reports").json()["reports"]
        assert lst[0]["status"] == "failed"
        assert "生成失败" in lst[0]["summary_first_paragraph"]
        detail = client.get(f"/api/review/reports/{lst[0]['id']}").json()
        assert "生成失败" in detail["summary_md"]

    def test_weekly_default_period_and_idempotent_overwrite(self, client, some_records, monkeypatch):
        _mock_deepseek(monkeypatch)
        r = client.post("/api/review/reports/generate", json={"report_type": "weekly"})
        assert r.status_code == 200
        assert r.json()["period_end"] > r.json()["period_start"]

        # 再次生成同一周：不新增行，覆盖同一报告
        r2 = client.post("/api/review/reports/generate", json={"report_type": "weekly"})
        assert r2.json()["id"] == r.json()["id"]
        assert len(client.get("/api/review/reports", params={"type": "weekly"}).json()["reports"]) == 1

    def test_report_404(self, client):
        assert client.get("/api/review/reports/nope").status_code == 404


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/review/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_default_period_is_yesterday_for_daily_and_last_week_for_weekly():
    """09:00 调度生成时回顾刚结束的周期：daily=昨天，weekly=上周一~周日。"""
    from datetime import date, timedelta
    from src.api.routes import _period_range

    today = date.today()
    ds, de = _period_range("daily", None, None)
    assert (ds, de) == ((today - timedelta(days=1)).isoformat(),) * 2
    ws, we = _period_range("weekly", None, None)
    last_monday = today - timedelta(days=today.weekday()) - timedelta(days=7)
    assert ws == last_monday.isoformat() and we == (last_monday + timedelta(days=6)).isoformat()


def test_projects_window_and_hidden_buckets(client, auth_headers):
    """/projects：窗口统计、活动量降序、杂项桶隐藏、近 14 天逐日计数。"""
    from datetime import date, timedelta

    from fastapi.testclient import TestClient
    from src.main import app

    c = TestClient(app)
    recs = [
        {"machine": "nas", "kind": "session", "project": "personal-web", "external_id": f"p{i}",
         "title": f"t{i}", "started_at": (date.today() - timedelta(days=2-i)).isoformat() + "T09:00:00"} for i in range(3)
    ]
    recs.append({"machine": "nas", "kind": "session", "project": "personal-web", "external_id": "old",
                 "title": "old", "started_at": "2025-01-01T09:00:00"})
    recs.append({"machine": "nas", "kind": "session", "project": "default-workspace", "external_id": "j1",
                 "title": "j", "started_at": "2026-01-15T09:00:00"})
    for i in range(2):
        recs.append({"machine": "nas", "kind": "session", "project": "study", "external_id": f"s{i}",
                     "title": "s", "started_at": (date.today() - timedelta(days=1)).isoformat() + "T10:00:00"})
    assert c.post("/api/review/ingest/records", json={"records": recs}, headers=auth_headers).status_code == 200

    r = c.get("/api/review/projects?days=7")
    assert r.status_code == 200
    body = r.json()
    names = [p["project"] for p in body["projects"]]
    assert "default-workspace" not in names          # 杂项桶隐藏
    assert names[0] == "personal-web"                # 活动量降序
    top = body["projects"][0]
    assert top["session_count"] == 3                 # 只计窗口内
    assert top["active_days"] == 3
    assert len(top["daily_counts"]) == 14            # 固定 14 天条形数据
    assert sum(d["count"] for d in top["daily_counts"]) == 3  # 14 天条形窗口内只有近 3 条

    r_all = c.get("/api/review/projects?days=0")
    assert r_all.json()["projects"][0]["session_count"] == 4  # 全部含 old
