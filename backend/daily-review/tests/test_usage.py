"""usage：ledger 解析、ingest 幂等、GET /usage 聚合、generate prompt 含 usage 段。"""
import httpx
import pytest

from src.parser.usage import parse_usage_ledger

LEDGER = {
    "version": 1,
    "days": {
        "2026-11-27": {
            "deepseek-official": {
                "deepseek-flash": {
                    "inputTokens": 100, "outputTokens": 200,
                    "cacheReadTokens": 3000, "cacheWriteTokens": 0,
                    "reasoningTokens": 50, "calls": 10, "cost": 1.5,
                }
            }
        },
        "2026-11-28": {
            "deepseek-official": {
                # snake_case 兼容路径
                "deepseek-flash": {"input_tokens": 10, "output_tokens": 20, "calls": 1, "cost": 0.1}
            }
        },
    },
}


class TestLedgerParser:
    def _write(self, tmp_path, obj=None, raw=None):
        import json

        f = tmp_path / "usage-ledger.json"
        f.write_text(raw if raw is not None else json.dumps(obj), encoding="utf-8")
        return f

    def test_parse_flat(self, tmp_path):
        rows = parse_usage_ledger(self._write(tmp_path, LEDGER), machine="nas")
        assert len(rows) == 2
        r27 = next(r for r in rows if r["date"] == "2026-11-27")
        assert r27["machine"] == "nas"
        assert r27["provider"] == "deepseek-official"
        assert r27["model"] == "deepseek-flash"
        assert r27["input_tokens"] == 100
        assert r27["cache_read_tokens"] == 3000
        assert r27["calls"] == 10
        assert r27["cost"] == 1.5

    def test_corrupt_returns_empty(self, tmp_path):
        assert parse_usage_ledger(self._write(tmp_path, raw="{bad json")) == []

    def test_missing_file_returns_empty(self, tmp_path):
        assert parse_usage_ledger(tmp_path / "nope.json") == []

    def test_empty_ledger(self, tmp_path):
        assert parse_usage_ledger(self._write(tmp_path, {"version": 1, "days": {}})) == []


class TestUsageIngest:
    def _post(self, client, headers, **over):
        rec = {
            "machine": "windows", "date": "2026-11-27",
            "provider": "deepseek-official", "model": "deepseek-flash",
            "input_tokens": 100, "output_tokens": 200, "calls": 10, "cost": 1.5,
            **over,
        }
        return client.post("/api/review/ingest/usage", json={"usage": [rec]}, headers=headers)

    def test_requires_token(self, client):
        assert client.post("/api/review/ingest/usage", json={"usage": []}).status_code == 401

    def test_upsert_idempotent_overwrite(self, client, auth_headers):
        r1 = self._post(client, auth_headers)
        assert r1.json() == {"received": 1, "upserted": 1}
        # 同键重跑：仍 upserted=1（覆盖，不新增），cost 更新
        r2 = self._post(client, auth_headers, cost=2.0, calls=12)
        assert r2.json() == {"received": 1, "upserted": 1}
        data = client.get("/api/review/usage", params={"date": "2026-11-27"}).json()
        assert data["totals"]["cost"] == 2.0
        assert data["totals"]["calls"] == 12


class TestUsageQuery:
    def test_range_merge_two_machines_and_grouping(self, client, auth_headers):
        usage = [
            {"machine": "nas", "date": "2026-11-27", "provider": "p", "model": "m1",
             "input_tokens": 100, "output_tokens": 200, "calls": 3, "cost": 1.0},
            {"machine": "windows", "date": "2026-11-27", "provider": "p", "model": "m1",
             "input_tokens": 50, "output_tokens": 60, "calls": 2, "cost": 0.5},
            {"machine": "nas", "date": "2026-11-20", "provider": "p", "model": "m2",
             "input_tokens": 999, "output_tokens": 0, "calls": 1, "cost": 9.0},  # 窗口外
        ]
        client.post("/api/review/ingest/usage", json={"usage": usage}, headers=auth_headers)
        data = client.get(
            "/api/review/usage", params={"start": "2026-11-26", "end": "2026-11-28"}
        ).json()
        assert (data["start"], data["end"]) == ("2026-11-26", "2026-11-28")
        assert data["totals"]["input_tokens"] == 150  # 两机合并
        assert data["totals"]["cost"] == 1.5
        assert data["totals"]["calls"] == 5
        by_day = {(d["date"], d["machine"]): d for d in data["by_day_machine"]}
        assert by_day[("2026-11-27", "nas")]["input_tokens"] == 100
        assert by_day[("2026-11-27", "windows")]["input_tokens"] == 50
        assert len(data["by_model"]) == 2  # 按 (provider, model, machine) 分列
        assert all(m["model"] == "m1" for m in data["by_model"])

    def test_date_param_and_default_window(self, client, auth_headers):
        client.post("/api/review/ingest/usage", json={"usage": [
            {"machine": "nas", "date": "2026-11-27", "provider": "p", "model": "m",
             "input_tokens": 1, "calls": 1, "cost": 0.1},
        ]}, headers=auth_headers)
        d = client.get("/api/review/usage", params={"date": "2026-11-27"}).json()
        assert d["totals"]["input_tokens"] == 1
        assert client.get("/api/review/usage", params={"date": "bad"}).status_code == 400
        assert client.get("/api/review/usage").status_code == 200  # 默认最近 7 天


class TestGenerateWithUsage:
    def test_prompt_contains_usage_section(self, client, auth_headers, monkeypatch):
        client.post("/api/review/ingest/usage", json={"usage": [
            {"machine": "nas", "date": "2026-11-27", "provider": "deepseek-official",
             "model": "deepseek-flash", "input_tokens": 100, "output_tokens": 200,
             "calls": 10, "cost": 1.5},
        ]}, headers=auth_headers)

        calls = []

        def fake_post(url, **kw):
            calls.append(kw)
            return httpx.Response(
                200, request=httpx.Request("POST", url),
                json={"choices": [{"message": {"content": "# 日报"}}]},
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        r = client.post(
            "/api/review/reports/generate",
            json={"report_type": "daily", "period_start": "2026-11-27"},
        )
        assert r.status_code == 200
        prompt = calls[0]["json"]["messages"][1]["content"]
        assert "LLM 用量" in prompt
        assert "deepseek-flash" in prompt
        assert "$1.5" in prompt

    def test_prompt_without_usage_data(self, client, monkeypatch):
        calls = []

        def fake_post(url, **kw):
            calls.append(kw)
            return httpx.Response(
                200, request=httpx.Request("POST", url),
                json={"choices": [{"message": {"content": "# 日报"}}]},
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        r = client.post(
            "/api/review/reports/generate",
            json={"report_type": "daily", "period_start": "2026-11-27"},
        )
        assert r.status_code == 200
        assert "LLM 用量" not in calls[0]["json"]["messages"][1]["content"]
