"""经理 API 测试：TestClient + 内存库。"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.db.models import Base, Fund, Manager, ManagerTenure
from src.main import app


@pytest.fixture
def client(db_session):
    # 依赖注入：get_db 覆盖为测试内存库（与 test_api.py 同一模式）
    from src.db.session import get_db

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _mk_mgr(mid, name, company="华夏基金", career_years=10.0, scale=100.0,
            weighted=None, mdd=None, sharpe=None, calmar=None, n_managed=3):
    return Manager(
        manager_id=mid, name=name, company=company,
        career_days=int(career_years * 365.25), career_years=career_years,
        current_scale_yi=scale, current_fund_count=2, managed_fund_count=n_managed,
        tenure_weighted_annual=weighted, max_drawdown=mdd,
        sharpe=sharpe, calmar=calmar,
        representative_fund="000011", scope="stock_active",
    )


@pytest.fixture
def seeded(db_session):
    db_session.add_all([
        _mk_mgr("m1", "老将甲", weighted=12.0, mdd=-35.0, sharpe=0.9, calmar=0.34, career_years=15.0),
        _mk_mgr("m2", "老将乙", weighted=8.0, mdd=-65.0, sharpe=0.4, calmar=0.12, career_years=8.0),
        _mk_mgr("m3", "新人丙", weighted=20.0, mdd=-20.0, sharpe=1.2, calmar=1.0, career_years=2.0),
        _mk_mgr("m4", "空白丁", weighted=None, mdd=None, career_years=6.0),  # 指标缺失
    ])
    db_session.add(ManagerTenure(
        manager_id="m1", fund_code="000011", fund_name="基金A",
        fund_type="混合型-偏股", start_date=date(2012, 9, 28),
        tenure_days=5157, tenure_return=308.63, annual_return=10.48, is_current=True))
    # 让 /{code} 详情路由也有基金可查（验证路由不冲突）
    db_session.add(Fund(code="000011", name="基金A", is_active=True))
    db_session.commit()
    return db_session


class TestScreen:
    def test_lists_all(self, client, seeded):
        r = client.get("/api/funds/managers/screen")
        assert r.status_code == 200
        assert r.json()["total"] == 4

    def test_min_career_years_excludes_null_and_low(self, client, seeded):
        r = client.get("/api/funds/managers/screen", params={"min_career_years": 5})
        ids = {it["manager_id"] for it in r.json()["items"]}
        assert ids == {"m1", "m2", "m4"}  # 新人丙(2年)被排除

    def test_min_weighted_annual_null_not_matched(self, client, seeded):
        r = client.get("/api/funds/managers/screen", params={"min_weighted_annual": 5})
        ids = {it["manager_id"] for it in r.json()["items"]}
        assert ids == {"m1", "m2", "m3"}  # 空白丁(指标NULL)不命中

    def test_max_drawdown_absolute_value(self, client, seeded):
        """回撤阈值按绝对值：-65% 的经理过不了 60。"""
        r = client.get("/api/funds/managers/screen", params={"max_drawdown": 60})
        ids = {it["manager_id"] for it in r.json()["items"]}
        assert "m2" not in ids
        assert "m1" in ids

    def test_sort_weighted_annual_desc(self, client, seeded):
        r = client.get("/api/funds/managers/screen", params={"sort": "weighted_annual"})
        items = r.json()["items"]
        weighted = [it["weighted_annual"] for it in items if it["weighted_annual"] is not None]
        assert weighted == sorted(weighted, reverse=True)
        # NULL 排尾部
        assert items[-1]["weighted_annual"] is None

    def test_sort_max_drawdown_asc_prefers_small(self, client, seeded):
        r = client.get("/api/funds/managers/screen", params={"sort": "max_drawdown"})
        items = [it for it in r.json()["items"] if it["max_drawdown"] is not None]
        assert items[0]["manager_id"] == "m3"  # -20% 最浅在前

    def test_pagination_invariants(self, client, seeded):
        """分页契约：total 与 limit 无关；items ⊂ 全量。"""
        r_all = client.get("/api/funds/managers/screen", params={"limit": 2, "page": 1})
        assert r_all.json()["total"] == 4
        assert len(r_all.json()["items"]) == 2
        r_p2 = client.get("/api/funds/managers/screen", params={"limit": 2, "page": 2})
        assert len(r_p2.json()["items"]) == 2
        p1_ids = {it["manager_id"] for it in r_all.json()["items"]}
        p2_ids = {it["manager_id"] for it in r_p2.json()["items"]}
        assert not (p1_ids & p2_ids)  # 无重叠

    def test_invalid_sort_422(self, client, seeded):
        r = client.get("/api/funds/managers/screen", params={"sort": "1=1"})
        assert r.status_code == 422

    def test_keyword_match(self, client, seeded):
        r = client.get("/api/funds/managers/screen", params={"keyword": "老将"})
        assert r.json()["total"] == 2


class TestDetail:
    def test_detail_with_tenures(self, client, seeded):
        r = client.get("/api/funds/managers/m1")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "老将甲"
        assert len(body["tenures"]) == 1
        assert body["tenures"][0]["fund_code"] == "000011"
        assert body["tenures"][0]["is_current"] is True

    def test_404(self, client, seeded):
        assert client.get("/api/funds/managers/nope").status_code == 404

    def test_not_conflict_with_fund_detail_route(self, client, seeded):
        """/managers/{id} 与基金 /{code} 并存；基金详情仍可达。"""
        r = client.get("/api/funds/000011")
        assert r.status_code == 200
        assert r.json()["code"] == "000011"
