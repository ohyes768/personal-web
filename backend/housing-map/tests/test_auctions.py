import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.auction_fetcher import AuctionClient, normalize_auction
from src.services.auction_store import StoreLock, read_store
from src.services.auction_refresh import collect_auctions
from src.api.auction_routes import router


def detail(aid=1, **changes):
    return dict(auction_id=aid, object_id=10, area_code=330108,
                second_class="residence", object_title="杭州市滨江区倾城之恋花园19幢1901室",
                cell_name="倾城之恋", auction_status="done", deal_price=4760000,
                appraise_price=6290000, start_price=3680000, bid_times=2,
                end_time="2026-09-29 10:37:33", from_where="taobao",
                from_where_url="https://sf-item.taobao.com/sf_item/123.htm",
                auction_additional={"announcement": "<p>建筑面积：149.3平方米；联系电话13800000000</p>"},
                **changes)


class Client:
    def __init__(self, pages, fail=False):
        self.pages, self.fail = pages, fail

    def list_page(self, page):
        return self.pages[page - 1]

    def detail(self, aid):
        if self.fail:
            raise RuntimeError("upstream failed")
        return detail(aid)


def test_normalize_price_area_and_private_data():
    row = normalize_auction(detail(), [{"community_id": "c", "community_name": "倾城之恋花园", "community_alias": "倾城之恋"}])
    assert row["deal_price_yuan"] == 4760000
    assert row["area_m2"] == 149.3
    assert row["deal_unit_price"] == 31882
    assert row["community_id"] == "c"
    assert "13800000000" not in json.dumps(row)
    assert normalize_auction({**detail(), "auction_status": "abort"}, [])["deal_price_yuan"] is None
    assert normalize_auction({**detail(), "area_code": 330106}, []) is None


def test_collect_paginates_filters_and_keeps_old_rounds(tmp_path):
    path = tmp_path / "records.json"
    pages = [{"count": 3, "list": [{"auction_id": 1, "area_code": 330108}, {"auction_id": 2, "area_code": 330106}]},
             {"count": 3, "list": [{"auction_id": 3, "area_code": 330108}]}]
    result = collect_auctions(path, client=Client(pages), communities=[], delay=0)
    assert result["complete"] and result["saved"] == 2
    assert {r["auction_id"] for r in read_store(path)["records"]} == {"1", "3"}
    collect_auctions(path, client=Client([{"count": 1, "list": [{"auction_id": 4, "area_code": 330108}]}]), communities=[], delay=0)
    assert len(read_store(path)["records"]) == 3


def test_failure_and_cancellation_preserve_file(tmp_path):
    path = tmp_path / "records.json"
    path.write_text('{"version":1,"records":[]}', encoding="utf-8")
    before = path.read_bytes()
    pages = [{"count": 1, "list": [{"auction_id": 1, "area_code": 330108}]}]
    with pytest.raises(RuntimeError):
        collect_auctions(path, client=Client(pages, fail=True), communities=[], delay=0)
    assert path.read_bytes() == before
    with pytest.raises(InterruptedError):
        collect_auctions(path, client=Client(pages), communities=[], delay=0, cancelled=lambda: True)
    assert path.read_bytes() == before


def test_repeated_page_and_limits(tmp_path):
    page = {"count": 3, "list": [{"auction_id": 1, "area_code": 330108}]}
    with pytest.raises(RuntimeError, match="repeated"):
        collect_auctions(tmp_path / "r.json", client=Client([page, page]), communities=[], delay=0)
    result = collect_auctions(tmp_path / "r.json", client=Client([page]), communities=[], max_pages=1, delay=0)
    assert result["complete"] is False


def test_store_lock_excludes_other_process_handles(tmp_path):
    with StoreLock(tmp_path / "r.json"):
        with pytest.raises(BlockingIOError):
            with StoreLock(tmp_path / "r.json"):
                pass


def test_client_rejects_business_error():
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"status": 400, "data": []}
    class Session:
        def get(self, *args, **kwargs): return Response()
    with pytest.raises(RuntimeError):
        AuctionClient(session=Session(), attempts=1).list_page(1)


def test_client_accepts_digit_count():
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"status": 200, "data": {"count": "573", "list": []}}
    class Session:
        def get(self, *args, **kwargs): return Response()
    assert AuctionClient(session=Session()).list_page(1)["count"] == 573


def test_actual_status_enum_and_table_risk_extraction():
    payload = {**detail(), "auction_status": "failure", "obj_fact":
               "<table><tr><td>是否已腾空</td><td>已腾空</td></tr><tr><td>建筑面积</td><td>149.3平方米</td></tr></table>",
               "auction_additional": {}}
    row = normalize_auction(payload, [])
    assert row["status"] == "failure"
    assert row["area_m2"] == 149.3
    assert row["risk_notes"]["is_empty"] == "已腾空"


def test_refresh_job_and_cross_process_conflict(tmp_path, monkeypatch):
    from src.services import auction_refresh
    path = tmp_path / "r.json"
    monkeypatch.setattr(auction_refresh, "AUCTION_PATH", path)
    async def scenario():
        with StoreLock(path):
            assert not await auction_refresh.start_refresh(1, 1)
        def fake_collect(*args, **kwargs):
            import time
            while not kwargs["cancelled"]():
                time.sleep(0.01)
            raise InterruptedError()
        monkeypatch.setattr(auction_refresh, "collect_auctions", fake_collect)
        assert await auction_refresh.start_refresh(1, 1)
        assert not await auction_refresh.start_refresh(1, 1)
        assert auction_refresh.cancel_refresh()
        await auction_refresh._task
        assert auction_refresh.job["phase"] == "cancelled"
        assert not auction_refresh.job["running"]
    asyncio.run(scenario())


def test_query_and_refresh_validation(tmp_path, monkeypatch):
    from src.api import auction_routes
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"version": 1, "records": [normalize_auction(detail(), [])]}), encoding="utf-8")
    monkeypatch.setattr(auction_routes, "AUCTION_PATH", path)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as api:
        assert api.get("/api/auctions").json()["data"]["total"] == 1
        assert api.get("/api/auctions?status=unknown").json()["data"]["total"] == 0
        assert api.post("/api/auctions/refresh?max_pages=0").status_code == 422


def test_http_start_conflict_cancel_and_result(tmp_path, monkeypatch):
    from src.services import auction_refresh
    import time
    monkeypatch.setattr(auction_refresh, "AUCTION_PATH", tmp_path / "r.json")
    def fake_collect(*args, **kwargs):
        while not kwargs["cancelled"]():
            time.sleep(0.01)
        raise InterruptedError()
    monkeypatch.setattr(auction_refresh, "collect_auctions", fake_collect)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as api:
        assert api.post("/api/auctions/refresh?limit=1").status_code == 202
        assert api.post("/api/auctions/refresh").status_code == 409
        assert api.delete("/api/auctions/refresh").status_code == 200
        for _ in range(100):
            state = api.get("/api/auctions/refresh").json()["data"]
            if not state["running"]:
                break
            time.sleep(0.01)
        assert state["phase"] == "cancelled"
