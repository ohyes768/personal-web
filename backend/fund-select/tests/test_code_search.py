"""代码搜索（/screen?code= 与 /stock/screen?code=）契约测试

11-16-fund-code-search-list-result：搜索语义是「按代码取库里这一只」，
**故意不套阈值、不要求 is_active、不要求 ∈ 当前 tab 宇宙**。
本文件把这些「故意」锁成断言——谁把它们"补齐"成筛选语义就会红。
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import (
    Base, Fund, FundAchievementRank, FundFees, FundPerformance,
)
from src.services.filter_service import FilterService


def _mk(code: str, **kw) -> Fund:
    defaults = dict(
        code=code, name=f"基金{code}", fund_type="混合型-偏股",
        age_years=5.0, size_yi=10.0,
        mgr_name="张三", mgr_company="某基金公司",
        mgr_days=2000, mgr_experience_years=5.5,
        is_active=True,
        market_type="stock", market_subtype="混合型-偏股",
    )
    defaults.update(kw)
    return Fund(**defaults)


@pytest.fixture
def db(db_session):
    db_session.add_all([
        _mk("000001", name="优等生", size_yi=50.0, age_years=8.0),
        # 阈值全不达标：规模 0.5 亿 / 成立 0.6 年 / 经理 0.5 年
        _mk("000002", name="小破基", size_yi=0.5, age_years=0.6,
            mgr_experience_years=0.5),
        # 已清盘
        _mk("000003", name="已清盘基", is_active=False),
        # QDII（exclude_qdii 会剔掉）
        _mk("000004", name="QDII基", market_subtype="QDII-普通股票"),
        # 债基（股票 tab 宇宙外）
        _mk("000005", name="债基", market_type="bond", market_subtype="债券型-长债"),
    ])
    db_session.add_all([
        FundPerformance(code="000001", as_of_date=date(2026, 9, 1),
                        dd_3y=-5.0, ret_1y=10.0, ret_3y=30.0, ret_5y=60.0),
        FundPerformance(code="000002", as_of_date=date(2026, 9, 1),
                        dd_3y=-60.0, ret_1y=-20.0, ret_3y=-30.0, ret_5y=None),
        FundFees(code="000001", fee_mgmt=1.2, fee_custody=0.2),
        FundAchievementRank(code="000001", period_kind="阶段业绩", period="近3年",
                            as_of_date=date(2026, 9, 1),
                            ret=30.0, peer_rank="100/1000"),
    ])
    db_session.commit()
    return db_session


class TestSearchByCode:
    def test_hits_single_row(self, db):
        r = FilterService(db).search_by_code("000001", "stock")
        assert r["total"] == 1
        assert len(r["items"]) == 1
        assert r["items"][0]["code"] == "000001"

    def test_dto_shape_matches_screen(self, db):
        """搜索条目与列表条目同构：表格/文案才能完全复用。"""
        item = FilterService(db).search_by_code("000001", "stock")["items"][0]
        for k in ("code", "name", "fund_type", "market_subtype", "in_curated",
                  "size_yi", "age_years", "dd_3y", "ret_1y", "ret_3y", "ret_5y",
                  "sharpe", "mgr_name", "fee_annual",
                  "rank_ytd", "rank_1y", "rank_3y", "rank_5y"):
            assert k in item, f"DTO 缺字段 {k}"

    def test_rank_parsed(self, db):
        item = FilterService(db).search_by_code("000001", "stock")["items"][0]
        assert item["rank_3y"]["rank"] == 100
        assert item["rank_3y"]["total"] == 1000

    def test_thresholds_ignored(self, db):
        """000002 规模 0.5 亿 / 成立 0.6 年：常规筛选一定筛掉，搜索必须能搜到。"""
        normal = FilterService(db).screen_stock(
            min_size_yi=5, min_age=3, universe_codes=["000001", "000002"],
        )
        assert "000002" not in [it["code"] for it in normal["items"]]
        hit = FilterService(db).search_by_code("000002", "stock")
        assert hit["total"] == 1
        assert hit["items"][0]["code"] == "000002"

    def test_inactive_fund_still_returned(self, db):
        """代码搜索是查询动作：已清盘基金也能点开看历史。"""
        r = FilterService(db).search_by_code("000003", "stock")
        assert r["total"] == 1
        assert r["items"][0]["code"] == "000003"

    def test_outside_universe_still_returned(self, db):
        """不在股票宇宙的债基也返回（正常路径前端已先经 lookup 判 tab）。"""
        r = FilterService(db).search_by_code("000005", "stock")
        assert r["total"] == 1
        assert r["items"][0]["code"] == "000005"

    def test_unknown_code_returns_empty(self, db):
        r = FilterService(db).search_by_code("999999", "stock")
        assert r == {"total": 0, "items": []}

    def test_in_curated_flag(self, db, monkeypatch):
        monkeypatch.setattr(
            "src.services.filter_service.resolve_universe_codes",
            lambda kind, override=None: ["000001"],
        )
        assert FilterService(db).search_by_code("000001", "stock")["items"][0]["in_curated"] is True
        assert FilterService(db).search_by_code("000002", "stock")["items"][0]["in_curated"] is False


@pytest.fixture
def client(db):
    from src.db.session import get_db
    from src.main import app

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSearchByCodeApi:
    @pytest.mark.parametrize("base", ["/api/funds/screen", "/api/funds/stock/screen"])
    def test_code_param_hits(self, client, base):
        r = client.get(f"{base}?code=000001")
        assert r.status_code == 200
        b = r.json()
        assert b["total"] == 1
        assert b["items"][0]["code"] == "000001"

    @pytest.mark.parametrize("base", ["/api/funds/screen", "/api/funds/stock/screen"])
    def test_code_param_beats_thresholds(self, client, base):
        """URL 同时带代码和一组不可能满足的阈值：仍返回该条。"""
        r = client.get(
            f"{base}?code=000002&min_size_yi=999&min_age=99"
            "&max_dd_3y=0.1&min_mgr_exp=99&min_sharpe=9.9&exclude_qdii=true"
        )
        assert r.status_code == 200
        b = r.json()
        assert b["total"] == 1, "搜索态必须忽略阈值"
        assert b["items"][0]["code"] == "000002"

    def test_code_param_bypasses_exclude_qdii(self, client):
        b = client.get("/api/funds/stock/screen?code=000004&exclude_qdii=true").json()
        assert b["total"] == 1
        assert b["items"][0]["code"] == "000004"

    def test_unknown_code_empty(self, client):
        b = client.get("/api/funds/stock/screen?code=999999").json()
        assert b["total"] == 0
        assert b["items"] == []

    @pytest.mark.parametrize("bad", ["abc", "12345", "1234567", "00000a"])
    @pytest.mark.parametrize("base", ["/api/funds/screen", "/api/funds/stock/screen"])
    def test_invalid_code_422(self, client, base, bad):
        assert client.get(f"{base}?code={bad}").status_code == 422

    def test_no_code_param_unchanged(self, client):
        """不带 code：老筛选链路一字不改（默认 curated=空名单 → 0 条）。"""
        b = client.get("/api/funds/stock/screen").json()
        assert b["total"] == 0, "没注入 yaml 名单时应为空，证明没走搜索短路"
