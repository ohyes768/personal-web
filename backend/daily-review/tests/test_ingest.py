"""ingest 幂等 + token 鉴权测试。"""
import pytest


def _rec(external_id="s-1", machine="windows", **kw):
    return {
        "machine": machine,
        "kind": "session",
        "project": "personal-web",
        "external_id": external_id,
        "session_id": external_id,
        "title": "测试会话",
        "summary_text": "做了一些事",
        "started_at": "2026-11-27T01:00:00Z",
        "ended_at": "2026-11-27T02:00:00Z",
        "payload": {"tool_event_count": 3},
        **kw,
    }


class TestToken:
    def test_missing_token_rejected(self, client):
        r = client.post("/api/review/ingest/records", json={"records": [_rec()]})
        assert r.status_code == 401

    def test_wrong_token_rejected(self, client):
        r = client.post(
            "/api/review/ingest/records",
            json={"records": []},
            headers={"X-Ingest-Token": "wrong"},
        )
        assert r.status_code == 401

    def test_ingest_disabled_without_token_config(self, client, monkeypatch):
        from src import config

        monkeypatch.setattr(config, "get_ingest_token", lambda: "")
        import src.api.routes as routes

        monkeypatch.setattr(routes, "get_ingest_token", lambda: "")
        r = client.post("/api/review/ingest/records", json={"records": []})
        assert r.status_code == 503


class TestIngestIdempotency:
    def test_batch_upsert_and_skip(self, client, auth_headers):
        body = {"records": [_rec(), _rec(external_id="s-2")]}
        r1 = client.post("/api/review/ingest/records", json=body, headers=auth_headers)
        assert r1.status_code == 200
        assert r1.json() == {"received": 2, "inserted": 2, "skipped": 0}

        # 同批重传：全部 skipped
        r2 = client.post("/api/review/ingest/records", json=body, headers=auth_headers)
        assert r2.json() == {"received": 2, "inserted": 0, "skipped": 2}

        # 混合：一个新 + 一个重复
        r3 = client.post(
            "/api/review/ingest/records",
            json={"records": [_rec(), _rec(external_id="s-3")]},
            headers=auth_headers,
        )
        assert r3.json() == {"received": 2, "inserted": 1, "skipped": 1}

    def test_records_queryable(self, client, auth_headers):
        client.post("/api/review/ingest/records", json={"records": [_rec()]}, headers=auth_headers)
        r = client.get("/api/review/today", params={"date": "2026-11-27"})
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["machine"] == "windows"
        assert items[0]["kind"] == "session"

    def test_bad_date_format(self, client):
        assert client.get("/api/review/today", params={"date": "not-a-date"}).status_code == 400
