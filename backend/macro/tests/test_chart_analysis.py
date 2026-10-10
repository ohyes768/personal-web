"""Paid analysis regression checks use a fake model; no provider calls or secrets."""
import asyncio
import json
import os
from datetime import date

os.environ.setdefault("FRED_API_KEY", "analysis-tests")

import httpx
import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.analysis import auth, deepseek, routes, sessions
from src.analysis.registry import CHARTS, ChartDefinition, SeriesDefinition
from src.analysis.snapshot import build_snapshot
from src.config import Settings
from src.services import data_service


@pytest.fixture
def settings(monkeypatch, tmp_path):
    value = Settings(fred_api_key="test", data_dir=str(tmp_path), analysis_password="demo-password",
                     analysis_signing_secret="a-long-test-secret-never-used-in-production", deepseek_api_key="fake-key",
                     analysis_cookie_secure=False)
    for module in (auth, routes, sessions, deepseek):
        monkeypatch.setattr(module, "get_settings", lambda: value)
    monkeypatch.setattr(data_service, "settings", value)
    auth._attempts.clear()
    auth._revoked.clear()
    return value


@pytest.fixture
def observations(settings):
    days = pd.date_range("2026-01-01", periods=6)
    pd.DataFrame({"中国10y": [2.0, 2.1, None, 2.2, 2.3, 2.4],
                  "中国10年-2年": [0.5, 0.6, 0.7, None, 0.8, 0.9]}, index=days).to_csv(settings.data_dir + "/china_bond.csv")
    pd.DataFrame({"dr007": [1.8, 1.9]}, index=days[:2]).to_csv(settings.data_dir + "/dr007.csv")
    return data_service.DataService()


def test_raw_snapshot_common_dates_units_and_missing(settings, observations):
    snap = build_snapshot(CHARTS["rates.china-bonds"], date(2026, 1, 1), date(2026, 1, 6), observations)
    assert snap["decomposition"]["count"] == 4  # No forward fill.
    assert snap["decomposition"]["spread_change_bp"] == 40
    assert snap["decomposition"]["cn_10y_change_bp"] == 40
    assert snap["decomposition"]["cn_2y_change_bp"] == 0
    assert snap["derived"][0]["derived"] is True
    assert snap["references"][0]["statistics"]["end"]["date"] == "2026-01-02"
    again = build_snapshot(CHARTS["rates.china-bonds"], date(2026, 1, 1), date(2026, 1, 6), observations)
    assert snap["snapshot_id"] == again["snapshot_id"]
    frame = pd.read_csv(observations.files["china_bond"], index_col=0)
    frame.iloc[-1, 0] = 2.5
    frame.to_csv(observations.files["china_bond"])
    changed = build_snapshot(CHARTS["rates.china-bonds"], date(2026, 1, 1), date(2026, 1, 6), observations)
    assert changed["snapshot_id"] != snap["snapshot_id"]


def test_bad_or_absent_observations_never_fabricate(settings, observations):
    with pytest.raises(HTTPException) as exc:
        build_snapshot(CHARTS["rates.china-bonds"], date(2025, 1, 1), date(2025, 1, 6), observations)
    assert exc.value.status_code == 422
    observations.files["china_bond"].write_text('date,x\nnot-a-date,5\n')
    with pytest.raises(HTTPException) as exc:
        build_snapshot(CHARTS["rates.china-bonds"], date(2026, 1, 1), date(2026, 1, 6), observations)
    assert exc.value.status_code == 503


def test_second_chart_uses_same_snapshot_pipeline(settings, observations):
    definition = ChartDefinition("test.dual", "双轴", "说明", (
        SeriesDefinition("ten", "测试非利率单位", "china_bond", "中国10y", "点"),
        SeriesDefinition("missing", "缺失", "china_bond", "absent")))
    snap = build_snapshot(definition, date(2026, 1, 1), date(2026, 1, 6), observations)
    assert snap["quality"] == "partial"
    assert snap["primary"][1]["status"] == "missing"
    assert snap["primary"][0]["statistics"]["count"] == 5
    assert snap["primary"][0]["unit"] == "点"
    assert snap["primary"][0]["statistics"]["change_bp"] is None


def test_read_during_write_is_retryable(settings, observations, monkeypatch):
    original = pd.read_csv
    def changing_read(path, *args, **kwargs):
        frame = original(path, *args, **kwargs)
        with open(path, "a") as target:
            target.write("\n")
        return frame
    monkeypatch.setattr(pd, "read_csv", changing_read)
    with pytest.raises(RuntimeError):
        observations.load_analysis_observations(["china_bond", "dr007"])


@pytest.fixture
def client(settings, observations, monkeypatch):
    async def fake(messages):
        assert messages[0]["role"] == "system"
        yield {"kind": "delta", "text": "利差扩大了。[cn_10y_2y]"}
        yield {"kind": "usage", "usage": {"total_tokens": 25}}
    monkeypatch.setattr(routes, "store", sessions.SessionStore(fake))
    monkeypatch.setattr(routes, "get_data_service", lambda: observations)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as value:
        yield value


def unlock(client):
    assert client.post("/api/analysis/auth/unlock", json={"password": "demo-password"}).status_code == 200


def create(client):
    return client.post("/api/analysis/sessions", json={"chart_id": "rates.china-bonds", "start_date": "2026-01-01", "end_date": "2026-01-06"})


def test_auth_expiry_password_change_origin_lock(client, settings, monkeypatch):
    assert create(client).status_code == 401
    assert client.post("/api/analysis/auth/unlock", json={"password": "wrong"}).status_code == 401
    cross = client.post("/api/analysis/auth/unlock", headers={"Origin": "https://evil.example"}, json={"password": "demo-password"})
    assert cross.status_code == 403
    response = client.post("/api/analysis/auth/unlock", json={"password": "demo-password"})
    assert "HttpOnly" in response.headers["set-cookie"] and "Max-Age=604800" in response.headers["set-cookie"]
    token = client.cookies.get(auth.COOKIE)
    assert client.get("/api/analysis/auth").json()["unlocked"]
    settings.analysis_password = "changed"
    assert create(client).status_code == 401
    settings.analysis_password = "demo-password"
    assert client.post("/api/analysis/auth/lock").status_code == 200
    client.cookies.set(auth.COOKIE, token)
    assert create(client).status_code == 401
    client.cookies.clear()
    unlock(client)
    real_time = auth.time.time
    monkeypatch.setattr(auth.time, "time", lambda: real_time() + auth.LIFETIME + 1)
    assert create(client).status_code == 401


def test_api_stream_replay_and_conversation_ownership(client):
    unlock(client)
    response = create(client)
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    body = {"request_id": "first-request", "message": "请分析"}
    text = client.post(f"/api/analysis/sessions/{session_id}/messages", json=body).text
    assert '"kind": "done"' in text and '利差扩大了' in text
    replay = client.post(f"/api/analysis/sessions/{session_id}/messages", json=body)
    assert replay.text == text
    assert len(routes.store.sessions[session_id].history) == 2
    result = client.get(f"/api/analysis/sessions/{session_id}/requests/first-request").json()
    assert result["status"] == "complete"
    client.cookies.clear()
    unlock(client)  # Distinct unlock gets a distinct owner.
    assert client.get(f"/api/analysis/sessions/{session_id}/requests/first-request").status_code == 404


def test_session_failure_cancel_concurrency_and_expiry(settings):
    async def scenario():
        gate = asyncio.Event()
        async def slow(messages):
            yield {"kind": "delta", "text": "partial"}
            await gate.wait()
            yield {"kind": "delta", "text": "done"}
        store = sessions.SessionStore(slow)
        session = store.create("owner", {"snapshot_id": "test"}, CHARTS["rates.china-bonds"])
        gen = store.start(session, "req-0001", "question")
        assert store.start(session, "req-0001", "question") is gen
        with pytest.raises(HTTPException) as exc:
            store.start(session, "req-0002", "question")
        assert exc.value.status_code == 409
        await asyncio.sleep(0)
        gen.cancel()
        await gen.task
        assert gen.status == "cancelled" and session.history == []
        async def fail(messages):
            yield {"kind": "delta", "text": "unfinished"}
            raise RuntimeError("secret should never escape")
        store.stream = fail
        failed = store.start(session, "req-0003", "question")
        await failed.task
        assert failed.status == "failed" and not session.history
        assert "secret" not in json.dumps(failed.events)
        session.touched -= 1801
        with pytest.raises(HTTPException) as exc:
            store.get(session.id, "owner")
        assert exc.value.status_code == 410
    asyncio.run(scenario())


@pytest.mark.parametrize("reason", ["stop", "length", None])
def test_provider_parser_handles_chunks_and_truncation(settings, monkeypatch, reason):
    async def scenario(reason):
        async def handler(request):
            body = json.loads(request.content)
            assert body["thinking"] == {"type": "disabled"}
            assert body["stream"]
            content = 'data: ' + json.dumps({"choices": [{"delta": {"reasoning_content": "hidden", "content": "hello"}, "finish_reason": reason}]}) + '\n\ndata: [DONE]\n\n'
            return httpx.Response(200, text=content)
        factory = httpx.AsyncClient
        monkeypatch.setattr(deepseek.httpx, "AsyncClient", lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs))
        return [event async for event in deepseek.stream_answer([{"role": "user", "content": "hi"}])]
    if reason == "stop":
        assert asyncio.run(scenario(reason)) == [{"kind": "delta", "text": "hello"}]
    else:
        with pytest.raises(ValueError):
            asyncio.run(scenario(reason))


def test_cancel_before_task_start_and_global_capacity(settings):
    async def scenario():
        async def slow(messages):
            await asyncio.Event().wait()
            yield {"kind": "delta", "text": "never"}
        store = sessions.SessionStore(slow)
        definition = CHARTS["rates.china-bonds"]
        first = store.create("owner", {"snapshot_id": "1"}, definition)
        gen = store.start(first, "request-first", "q")
        gen.cancel()  # Cancellation before the coroutine gets its first turn.
        await asyncio.gather(gen.task, return_exceptions=True)
        assert gen.status == "cancelled" and first.history == []
        second = store.create("owner", {"snapshot_id": "2"}, definition)
        third = store.create("owner", {"snapshot_id": "3"}, definition)
        one = store.start(first, "request-new", "q")
        two = store.start(second, "request-two", "q")
        with pytest.raises(HTTPException) as exc:
            store.start(third, "request-three", "q")
        assert exc.value.status_code == 429
        store.lock_owner("owner")
        await asyncio.gather(one.task, two.task, return_exceptions=True)
        assert not store.sessions
    asyncio.run(scenario())


def test_password_attempt_throttling(client):
    for _ in range(5):
        assert client.post("/api/analysis/auth/unlock", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/analysis/auth/unlock", json={"password": "wrong"}).status_code == 429


def test_total_generation_timeout_leaves_no_history(settings):
    async def scenario():
        settings.analysis_timeout_seconds = .01
        async def slow(messages):
            yield {"kind": "delta", "text": "unfinished"}
            await asyncio.sleep(1)
        store = sessions.SessionStore(slow)
        session = store.create("owner", {"snapshot_id": "test"}, CHARTS["rates.china-bonds"])
        gen = store.start(session, "request-timeout", "q")
        await gen.task
        assert gen.status == "failed" and session.history == []
    asyncio.run(scenario())


def test_origin_requires_public_port(settings):
    from starlette.requests import Request
    request = Request({"type": "http", "method": "POST", "scheme": "https", "path": "/", "server": ("web.example", 9443),
                       "headers": [(b"host", b"web.example:9443"), (b"origin", b"https://web.example:9443")]})
    auth.check_origin(request)
    stripped = Request({"type": "http", "method": "POST", "scheme": "https", "path": "/", "server": ("web.example", 443),
                        "headers": [(b"host", b"web.example"), (b"origin", b"https://web.example:9443")]})
    with pytest.raises(HTTPException) as exc:
        auth.check_origin(stripped)
    assert exc.value.status_code == 403


@pytest.mark.parametrize('chart_id', list(CHARTS))
def test_fixed_panels_raw_csv_units_and_missing(settings, chart_id):
    definition = CHARTS[chart_id]
    days = pd.date_range('2026-01-01', periods=6)
    columns = {}
    service = data_service.DataService()
    for item in (*definition.series, *definition.references):
        columns.setdefault(item.store, {})[item.column] = [10, 11, None, 13, 14, 15]
    for store, values in columns.items():
        pd.DataFrame(values, index=days).to_csv(service.files[store])
    snap = build_snapshot(definition, date(2026, 1, 1), date(2026, 1, 6), service)
    assert snap['common_dates']['count'] == 5
    assert [s['evidence_id'] for s in snap['primary']] == [s.id for s in definition.series]
    for item, evidence in zip(definition.series, snap['primary']):
        assert evidence['unit'] == item.unit
        assert evidence['statistics']['count'] == 5
        assert evidence['statistics']['change_bp'] == (500 if item.unit == '%' and item.is_rate else None)
    missing = definition.series[-1]
    frame = pd.read_csv(service.files[missing.store], index_col=0).drop(columns=missing.column)
    frame.to_csv(service.files[missing.store])
    if len(definition.series) > 1:
        partial = build_snapshot(definition, date(2026, 1, 1), date(2026, 1, 6), service)
        assert partial['primary'][-1]['status'] == 'missing'
        assert partial['quality'] == 'partial'


def test_market_dual_axes_distinct_calendars(settings):
    service = data_service.DataService()
    days = pd.date_range('2026-01-01', periods=6)
    pd.DataFrame({'total_amount_yi': [100, 200, 300, 400, 500, 600]}, index=days).to_csv(service.files['volume'])
    pd.DataFrame({'margin_balance_yi': [1000, 1100, 1200]}, index=days[::2]).to_csv(service.files['margin'])
    pd.DataFrame({'turnover_rate': [1, 2, 3, 4, 5, 6]}, index=days).to_csv(service.files['turnover'])
    snap = build_snapshot(CHARTS['market-sentiment'], date(2026, 1, 1), date(2026, 1, 6), service)
    assert snap['primary'][1]['statistics']['count'] == 3
    assert snap['primary'][2]['statistics']['change_pp'] == 5
    assert snap['primary'][2]['statistics']['change_bp'] is None
    assert snap['common_dates']['count'] == 3
    assert snap['common_dates']['series'][0]['statistics']['end']['date'] == '2026-01-05'
    assert snap['primary'][0]['statistics']['end']['date'] == '2026-01-06'


def test_registry_matches_frontend_panels():
    from pathlib import Path
    import re
    root = Path(__file__).resolve().parents[3] / 'apps/macro/src/app/modules/economic/components'
    ids = {'market-sentiment', 'fund-flow'}
    for name in ('RatesChart', 'EconomicChart', 'LiquidityChart', 'CommodityChart', 'StockIndexChart'):
        ids.update(re.findall(r"id: '([a-z-]+\.[a-z-]+)'", (root / (name + '.tsx')).read_text()))
    assert ids == set(CHARTS)


def test_relative_changes_nonpositive_baselines():
    from src.analysis.snapshot import summarize
    days = pd.date_range('2026-01-01', periods=2)
    result = summarize('fx', '汇率', pd.Series([7, 7.7], index=days), unit='人民币/美元', relative_change=True)
    assert result['statistics']['change_percent'] == 10
    assert result['statistics']['change_bp'] is None
    for values in ([0, 1], [-1, 1], [1, -1]):
        result = summarize('oil', '原油', pd.Series(values, index=days), unit='美元/桶', relative_change=True)
        assert result['statistics']['change_percent'] is None


def test_long_multicurve_snapshot_fits_first_turn_budget(settings):
    from src.analysis.registry import DAILY_SERIES
    service = data_service.DataService()
    days = pd.bdate_range('2020-01-01', '2026-01-06')
    columns = {}
    for item in DAILY_SERIES.values():
        columns.setdefault(item.store, {})[item.column] = [100.123456789 + i * .0123456789 for i in range(len(days))]
    for store, values in columns.items():
        pd.DataFrame(values, index=days).to_csv(service.files[store])
    for definition in CHARTS.values():
        snap = build_snapshot(definition, date(2020, 1, 1), date(2026, 1, 5), service)
        assert all(item['source_as_of'] == '2026-01-06' for item in snap['primary'])
        assert all(item['statistics']['end']['date'] == '2026-01-05' for item in snap['primary'])
        assert len(json.dumps(snap, ensure_ascii=False)) + len(deepseek.SYSTEM) + len(definition.strategy) + 100 < 32000
