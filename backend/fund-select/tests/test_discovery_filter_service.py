"""
市场 tab 筛选单测（discovery-bond / discovery-stock）

关键回归点：
- 现有 bond/stock screen / universe_stats 接口行为不变
- 新 discovery 接口按 market_type 过滤
- 自定义 market_type 缩窄生效
"""
from src.services.filter_service import FilterService


def _mk_fund(code: str, market_type: str, **kw):
    from src.db.models import Fund
    defaults = dict(
        code=code,
        name=f"基金{code}",
        fund_type=kw.pop("fund_type", "债券型-长期纯债"),
        market_type=market_type,
        age_years=kw.pop("age_years", 5.0),
        size_yi=kw.pop("size_yi", 10.0),
        mgr_name=kw.pop("mgr_name", "张三"),
        mgr_company=kw.pop("mgr_company", "某基金公司"),
        mgr_days=kw.pop("mgr_days", 3650),
        mgr_experience_years=kw.pop("mgr_experience_years", 10.0),
        is_active=kw.pop("is_active", True),
    )
    defaults.update(kw)
    return Fund(**defaults)


class TestScreenDiscoveryBond:
    def test_default_universe_includes_bond_types(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_type="债券型"),
            _mk_fund("000002", market_type="定开债券"),
            _mk_fund("000003", market_type="股票型"),  # 不在 universe
            _mk_fund("000004", market_type="货币型"),  # 不在 universe
            _mk_fund("000005", market_type="债券型", is_active=False),  # inactive
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_bond()
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002"}

    def test_custom_market_type_narrows(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_type="债券型"),
            _mk_fund("000002", market_type="定开债券"),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_bond(market_types=["债券型"])
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001"}

    def test_empty_market_types_returns_zero(self, db_session):
        db_session.add(_mk_fund("000001", market_type="债券型"))
        db_session.commit()

        r = FilterService(db_session).screen_discovery_bond(market_types=[])
        assert r["total"] == 0
        assert r["items"] == []

    def test_filters_combine_with_market_type(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_type="债券型", age_years=10, size_yi=50),
            _mk_fund("000002", market_type="债券型", age_years=1, size_yi=10),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_bond(min_age=5)
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001"}


class TestScreenDiscoveryStock:
    def test_default_universe_includes_stock_types(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_type="股票型"),
            _mk_fund("000002", market_type="指数型"),
            _mk_fund("000003", market_type="混合型"),
            _mk_fund("000004", market_type="QDII"),
            _mk_fund("000005", market_type="债券型"),  # 不在 universe
            _mk_fund("000006", market_type="货币型"),  # 不在 universe
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_stock()
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002", "000003", "000004"}

    def test_custom_market_type_excludes_default(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_type="股票型"),
            _mk_fund("000002", market_type="QDII"),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_stock(market_types=["QDII"])
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000002"}

    def test_default_sort_ret_5y_desc(self, db_session):
        from src.db.models import FundPerformance
        import datetime
        db_session.add_all([
            _mk_fund("000001", market_type="股票型"),
            _mk_fund("000002", market_type="股票型"),
        ])
        db_session.add_all([
            FundPerformance(code="000001", as_of_date=datetime.date(2026, 9, 1), ret_5y=10.0),
            FundPerformance(code="000002", as_of_date=datetime.date(2026, 9, 1), ret_5y=30.0),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_stock()
        assert r["items"][0]["code"] == "000002"
        assert r["items"][1]["code"] == "000001"


class TestUniverseStatsDiscovery:
    def test_bond_kind_counts_only_bond_universe(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_type="债券型"),
            _mk_fund("000002", market_type="债券型"),
            _mk_fund("000003", market_type="股票型"),
        ])
        db_session.commit()

        r = FilterService(db_session).universe_stats("discovery-bond")
        assert r["total"] == 2

    def test_stock_kind_counts_only_stock_universe(self, db_session):
        """discovery-stock universe = [股票型、指数型、混合型、QDII]；债券型不在内"""
        db_session.add_all([
            _mk_fund("000001", market_type="股票型"),
            _mk_fund("000002", market_type="QDII"),
            _mk_fund("000003", market_type="债券型"),
            _mk_fund("000004", market_type="货币型"),
        ])
        db_session.commit()

        r = FilterService(db_session).universe_stats("discovery-stock")
        assert r["total"] == 2  # 仅 000001、000002

    def test_inactive_excluded_from_stats(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_type="债券型"),
            _mk_fund("000002", market_type="债券型", is_active=False),
        ])
        db_session.commit()

        r = FilterService(db_session).universe_stats("discovery-bond")
        assert r["total"] == 1


class TestRegressionExistingTabs:
    """回归：现有 bond/stock tab 行为不变"""

    def test_bond_screen_ignores_market_type(self, db_session, monkeypatch):
        """老 bond tab 不应被 market_type 字段干扰"""
        # 模拟老 yaml 名单
        monkeypatch.setattr(
            "src.data.fund_universe.load_fund_codes",
            lambda *args, **kwargs: ["000001", "000002"],
        )
        db_session.add_all([
            _mk_fund("000001", market_type="债券型", fund_type="中长期纯债"),
            _mk_fund("000002", market_type="股票型", fund_type="股票型"),  # market_type 异类，bond tab 仍要返回（按 yaml）
            _mk_fund("000003", market_type="债券型", fund_type="中长期纯债"),  # 不在 yaml
        ])
        db_session.commit()

        r = FilterService(db_session).screen()
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002"}

    def test_unknown_kind_raises(self, db_session):
        import pytest
        with pytest.raises(ValueError, match="unknown"):
            FilterService(db_session)._screen(
                kind="bogus",
                min_age=None, min_size_yi=None, max_dd_3y=None, min_mgr_exp=None,
                sort="size_yi", order="desc", universe_codes=None,
            )
