"""经理 API 测试：TestClient + 内存库。"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.db.models import Fund, Manager, ManagerTenure
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


class TestRefreshRoutes:
    """刷新端点（11-11）：路由顺序 + 单飞 + 状态轮询口径。"""

    def test_refresh_status_404_when_no_run(self, client, seeded):
        r = client.get("/api/funds/managers/refresh/status", params={"task_id": "nope"})
        assert r.status_code == 404

    def test_refresh_status_reads_run(self, client, db_session, seeded):
        from src.db.models import RefreshRun
        db_session.add(RefreshRun(task_id="t1", status="running", total=10, completed=3, failed=1))
        db_session.commit()
        r = client.get("/api/funds/managers/refresh/status", params={"task_id": "t1"})
        assert r.status_code == 200
        assert r.json() == {
            "task_id": "t1", "status": "running", "total": 10,
            "completed": 3, "failed": 1, "errors": [],
        }

    def test_refresh_status_errors_parsed_as_list(self, client, db_session, seeded):
        """errors 列是 JSON 数组字符串；非 JSON 旧行降级成单元素列表，不 500。"""
        from src.db.models import RefreshRun
        db_session.add_all([
            RefreshRun(task_id="tj", status="partial", errors='["m1: 超时", "m2: 404"]'),
            RefreshRun(task_id="tb", status="error", errors="裸文本错误"),
        ])
        db_session.commit()
        assert client.get("/api/funds/managers/refresh/status",
                          params={"task_id": "tj"}).json()["errors"] == ["m1: 超时", "m2: 404"]
        assert client.get("/api/funds/managers/refresh/status",
                          params={"task_id": "tb"}).json()["errors"] == ["裸文本错误"]

    def test_refresh_route_not_swallowed_by_detail_route(self, client, seeded):
        """/managers/refresh 必须命中刷新端点，不能被 /{manager_id} 当成经理 ID 吞掉。"""
        paths = app.openapi()["paths"]
        assert "/api/funds/managers/refresh" in paths
        assert "/api/funds/managers/refresh/status" in paths
        # 顺序守卫：refresh 的注册必须早于 /{manager_id}（FastAPI 按序匹配）
        ordered = [p for p in paths if p.startswith("/api/funds/managers/")]
        assert ordered.index("/api/funds/managers/refresh") < ordered.index(
            "/api/funds/managers/{manager_id}"
        )

    def test_refresh_409_when_already_running(self, client, seeded, monkeypatch):
        """并发保护：已有采集在跑时返回 409，不重复起任务。"""
        from src.api import manager_routes as mr

        class _BusyLock:
            def acquire(self, blocking=True):
                return False

            def release(self):
                pass

        monkeypatch.setattr(mr, "_refresh_lock", _BusyLock())
        r = client.get("/api/funds/managers/refresh")
        assert r.status_code == 409


class TestSortLongestTenure:
    """最长任期列可排序（页面「最长任期」列原来错绑 managed_fund_count）。"""

    def test_sort_longest_tenure_years(self, client, db_session, seeded):
        from src.db.models import Manager
        for mid, years in (("m1", 3.0), ("m2", 9.5), ("m3", 6.0)):
            m = db_session.get(Manager, mid)
            m.longest_tenure_years = years
        db_session.commit()

        r = client.get("/api/funds/managers/screen", params={"sort": "longest_tenure_years"})
        assert r.status_code == 200
        got = [it["longest_tenure_years"] for it in r.json()["items"]
               if it["longest_tenure_years"] is not None]
        assert got == sorted(got, reverse=True)
        assert got[0] == 9.5


class TestDerivedMetrics:
    """派生指标（11-12 调研）：任期胜率 / 独管比例 / 代表作背离。"""

    @pytest.fixture
    def seeded_metrics(self, db_session, client):
        """构造可手算的场景：

        - m_calc：3 段任期 2 赢 1 输 → 胜率 66.7；在管 2 只，一只独管一只共管 → 独管 50
          加权 5 / 最长 18 → 背离 13.0
        - m_solo：2 段全赢 → 胜率 100；在管 1 只独管 → 独管 100
        - m_zero：任期全亏 → 胜率 0
        - m_noret：任期无回报数据 → 胜率 None（不命中筛选）
        """
        from src.db.models import Manager, ManagerTenure
        from datetime import date

        def tenure(mid, code, ret, current=True):
            return ManagerTenure(
                manager_id=mid, fund_code=code, fund_name=f"基金{code}",
                start_date=date(2020, 1, 1), tenure_days=1000,
                tenure_return=ret, annual_return=ret / 10, is_current=current)

        db_session.add_all([
            Manager(manager_id="m_calc", name="手算甲", company="华夏基金",
                    career_years=10, scope="stock_active",
                    tenure_weighted_annual=5.0, longest_tenure_annual=18.0),
            Manager(manager_id="m_solo", name="独管乙", company="华夏基金",
                    career_years=8, scope="stock_active",
                    tenure_weighted_annual=8.0, longest_tenure_annual=10.0),
            Manager(manager_id="m_zero", name="全亏丙", company="易方达基金",
                    career_years=6, scope="stock_active",
                    tenure_weighted_annual=-3.0, longest_tenure_annual=-1.0),
            Manager(manager_id="m_noret", name="无数据丁", company="易方达基金",
                    career_years=6, scope="stock_active"),
            # m_calc: 3 段（2 赢 1 输），在管 2 只（A 独管 + B 共管）
            tenure("m_calc", "000011", 50.0),                       # 赢，在管
            tenure("m_calc", "000022", 30.0),                       # 赢，在管（共管）
            tenure("m_calc", "000033", -10.0, current=False),       # 输，已离任
            # m_solo: 2 段全赢，1 只在管独管
            tenure("m_solo", "000044", 20.0),
            tenure("m_solo", "000055", 10.0, current=False),
            # m_zero: 2 段全亏
            tenure("m_zero", "000066", -5.0),
            tenure("m_zero", "000077", -8.0),
            # m_noret: 有任期但无回报
            ManagerTenure(manager_id="m_noret", fund_code="000088",
                          start_date=date(2020, 1, 1), tenure_days=500,
                          tenure_return=None, is_current=True),
            # 000022 第二位经理 → m_calc 的 000022 变共管
            tenure("m_solo", "000022", 12.0),
        ])
        db_session.commit()
        return db_session

    def _row(self, client, mid):
        items = client.get("/api/funds/managers/screen", params={"limit": 50}).json()["items"]
        return next(it for it in items if it["manager_id"] == mid)

    def test_win_rate_computed(self, client, seeded_metrics):
        row = self._row(client, "m_calc")
        assert row["tenure_win_rate"] == 66.7   # 2/3
        assert self._row(client, "m_solo")["tenure_win_rate"] == 100.0
        assert self._row(client, "m_zero")["tenure_win_rate"] == 0.0

    def test_win_rate_none_when_no_return_data(self, client, seeded_metrics):
        assert self._row(client, "m_noret")["tenure_win_rate"] is None

    def test_solo_ratio_computed(self, client, seeded_metrics):
        # m_calc 在管 2 只：000011 独管 + 000022 共管（m_solo 也在管） → 50%
        assert self._row(client, "m_calc")["solo_ratio"] == 50.0
        # m_solo 在管 2 只：000044 独管 + 000022 共管 → 50%
        assert self._row(client, "m_solo")["solo_ratio"] == 50.0

    def test_rep_divergence(self, client, seeded_metrics):
        row = self._row(client, "m_calc")
        assert row["rep_divergence"] == 13.0    # 18.0 - 5.0
        # 单边缺失 → None
        assert self._row(client, "m_noret")["rep_divergence"] is None

    def test_filter_min_win_rate_excludes_none(self, client, seeded_metrics):
        items = client.get("/api/funds/managers/screen",
                           params={"min_win_rate": 50, "limit": 50}).json()["items"]
        ids = {it["manager_id"] for it in items}
        assert ids == {"m_calc", "m_solo"}      # m_zero(0) 与 m_noret(None) 不命中

    def test_filter_min_solo_ratio(self, client, seeded_metrics):
        items = client.get("/api/funds/managers/screen",
                           params={"min_solo_ratio": 80, "limit": 50}).json()["items"]
        ids = {it["manager_id"] for it in items}
        assert "m_calc" not in ids and "m_solo" not in ids  # 都是 50%

    def test_sort_by_win_rate(self, client, seeded_metrics):
        items = client.get("/api/funds/managers/screen",
                           params={"sort": "tenure_win_rate", "limit": 50}).json()["items"]
        rates = [it["tenure_win_rate"] for it in items if it["tenure_win_rate"] is not None]
        assert rates == sorted(rates, reverse=True)
        assert rates[0] == 100.0

    def test_detail_includes_aggregates(self, client, seeded_metrics):
        body = client.get("/api/funds/managers/m_calc").json()
        assert body["tenure_win_rate"] == 66.7
        assert body["solo_ratio"] == 50.0
        assert body["rep_divergence"] == 13.0

    def test_paginated_manager_with_tenures(self, client, seeded):
        """既有 seeded 夹具（m1 有 1 段全赢任期）胜率 100，不回归。"""
        row = self._row(client, "m1")
        assert row["tenure_win_rate"] == 100.0


class TestMaxFundCount:
    """在管只数 ≤ N（11-12 默认分层：精力分散硬门槛，中基协上限 10）。"""

    def test_max_fund_count(self, client, db_session):
        from src.db.models import Manager
        db_session.add_all([
            Manager(manager_id="m_few", name="专注甲", current_fund_count=3, scope="stock_active"),
            Manager(manager_id="m_many", name="一拖多乙", current_fund_count=15, scope="stock_active"),
            Manager(manager_id="m_null", name="无数据丙", current_fund_count=None, scope="stock_active"),
        ])
        db_session.commit()
        items = client.get("/api/funds/managers/screen",
                           params={"max_fund_count": 8, "limit": 50}).json()["items"]
        ids = {it["manager_id"] for it in items}
        assert "m_few" in ids
        assert "m_many" not in ids
        assert "m_null" not in ids  # NULL 不命中，与其它筛选语义一致
