"""
市场 tab 筛选单测（discovery-bond / discovery-stock）

关键回归点：
- 现有 bond/stock screen / universe_stats 接口行为不变
- 新 discovery 接口按 market_subtype（akshare 子类）过滤
- 自定义 market_subtype 缩窄生效
"""
from src.services.filter_service import FilterService


def _mk_fund(code: str, market_subtype: str, market_type: str = "", **kw):
    from src.db.models import Fund
    from src.data.market_subtype_map import categorize
    defaults = dict(
        code=code,
        name=f"基金{code}",
        fund_type=kw.pop("fund_type", "债券型-长期纯债"),
        market_subtype=market_subtype,
        market_type=market_type or categorize(market_subtype),
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
    def test_default_universe_includes_bond_subtypes(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="债券型-中短债"),
            _mk_fund("000002", market_subtype="债券型-利率债"),
            _mk_fund("000003", market_subtype="指数型-固收"),    # 债指数 → 归 bond
            _mk_fund("000004", market_subtype="QDII-纯债"),      # 海外债 → 归 bond
            _mk_fund("000005", market_subtype="股票型"),         # 不在 universe
            _mk_fund("000006", market_subtype="FOF-稳健型"),     # 不在 universe
            _mk_fund("000007", market_subtype="债券型-中短债", is_active=False),  # inactive
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_bond()
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002", "000003", "000004"}

    def test_custom_market_subtype_narrows(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="债券型-中短债"),
            _mk_fund("000002", market_subtype="债券型-利率债"),
            _mk_fund("000003", market_subtype="指数型-固收"),
        ])
        db_session.commit()

        # 缩窄到单一子类
        r = FilterService(db_session).screen_discovery_bond(market_types=["债券型-中短债"])
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001"}

    def test_empty_market_types_returns_zero(self, db_session):
        db_session.add(_mk_fund("000001", market_subtype="债券型-中短债"))
        db_session.commit()

        r = FilterService(db_session).screen_discovery_bond(market_types=[])
        assert r["total"] == 0
        assert r["items"] == []

    def test_filters_combine_with_market_type(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="债券型-长期纯债", age_years=10, size_yi=50),
            _mk_fund("000002", market_subtype="债券型-长期纯债", age_years=1, size_yi=10),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_bond(min_age=5)
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001"}

    def test_partial_bond_included_when_mixed_coarse_selected(self, db_session):
        """回归（09-10-subtype-coverage-fix）：混合型-偏债 必须归 bond universe 且能通过 混合型 粗类别命中（债基侧）。"""
        db_session.add_all([
            _mk_fund("000001", market_subtype="混合型-偏债"),
            _mk_fund("000002", market_subtype="债券型-混合债"),
            _mk_fund("000003", market_subtype="混合型-偏股"),  # 归 stock，不在 bond universe
        ])
        db_session.commit()

        # 模拟前端展开：勾「混合型」（债基侧）→ 含 债券型-混合债 + 混合型-偏债
        expanded = ['债券型-混合债', '混合型-偏债']
        r = FilterService(db_session).screen_discovery_bond(market_types=expanded)
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002"}, f"债基混合型粗类别应不含偏股混合，实际: {codes}"

    def test_index_bond_routed_to_bond_not_stock(self, db_session):
        """关键回归：指数型-固收（债指数）必须归债基，不能错归股基 universe。"""
        db_session.add_all([
            _mk_fund("000001", market_subtype="指数型-固收"),       # 债指数
            _mk_fund("000002", market_subtype="指数型-海外股票"),  # 股指数
        ])
        db_session.commit()

        # 债基·市场 应包含 000001，不包含 000002
        bond_codes = {it["code"] for it in FilterService(db_session).screen_discovery_bond()["items"]}
        assert bond_codes == {"000001"}
        # 股基·市场 应包含 000002，不包含 000001
        stock_codes = {it["code"] for it in FilterService(db_session).screen_discovery_stock()["items"]}
        assert stock_codes == {"000002"}


class TestScreenDiscoveryStock:
    def test_default_universe_includes_stock_subtypes(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="股票型"),
            _mk_fund("000002", market_subtype="指数型-海外股票"),
            _mk_fund("000003", market_subtype="混合型-平衡"),
            _mk_fund("000004", market_subtype="QDII-普通股票"),
            _mk_fund("000005", market_subtype="债券型-中短债"),   # 不在 universe
            _mk_fund("000006", market_subtype="FOF-稳健型"),      # 不在 universe
            _mk_fund("000007", market_subtype="QDII-纯债"),       # 海外债，不在股基 universe
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_stock()
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002", "000003", "000004"}

    def test_custom_market_subtype_excludes_default(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="股票型"),
            _mk_fund("000002", market_subtype="QDII-普通股票"),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_stock(market_types=["QDII-普通股票"])
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000002"}

    def test_index_stock_included_when_index_coarse_selected(self, db_session):
        """回归（09-10-subtype-coverage-fix）：指数型-股票 必须归 stock universe 且能通过 指数型 粗类别命中。

        不修这条 case 时，勾「指数型」搜不到 5677 只 A 股 ETF / 指数增强主流基金。
        """
        db_session.add_all([
            _mk_fund("000001", market_subtype="指数型-股票"),
            _mk_fund("000002", market_subtype="指数型-海外股票"),
            _mk_fund("000003", market_subtype="指数型-其他"),
            _mk_fund("000004", market_subtype="股票型"),  # 对照：不在指数型里
        ])
        db_session.commit()

        # 模拟前端展开：勾「指数型」→ 3 种指数型 subtype 都包含
        expanded = ['指数型-海外股票', '指数型-其他', '指数型-股票']
        r = FilterService(db_session).screen_discovery_stock(market_types=expanded)
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002", "000003"}, f"指数型粗类别应命中 3 种 subtype，实际: {codes}"

        # 单独勾「指数型-股票」也能命中（前端展开正确性）
        r2 = FilterService(db_session).screen_discovery_stock(market_types=["指数型-股票"])
        codes2 = {it["code"] for it in r2["items"]}
        assert codes2 == {"000001"}

    def test_partial_stock_included_when_mixed_coarse_selected(self, db_session):
        """回归（09-10-subtype-coverage-fix）：混合型-偏股 必须归 stock universe 且能通过 混合型 粗类别命中。"""
        db_session.add_all([
            _mk_fund("000001", market_subtype="混合型-偏股"),
            _mk_fund("000002", market_subtype="混合型-平衡"),
            _mk_fund("000003", market_subtype="混合型-灵活"),
            _mk_fund("000004", market_subtype="混合型-偏债"),  # 归债基，不在 stock universe
        ])
        db_session.commit()

        expanded = ['混合型-平衡', '混合型-绝对收益', '混合型-灵活', '混合型-偏股']
        r = FilterService(db_session).screen_discovery_stock(market_types=expanded)
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002", "000003"}, f"混合型粗类别应不含偏债混合，实际: {codes}"

    def test_qdii_commodity_still_excluded_from_stock_universe(self, db_session):
        """回归（09-10-subtype-coverage-fix）：QDII-商品 / 商品 保持归 other，不进 stock universe。"""
        db_session.add_all([
            _mk_fund("000001", market_subtype="QDII-商品"),
            _mk_fund("000002", market_subtype="商品"),
            _mk_fund("000003", market_subtype="股票型"),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_stock()
        codes = {it["code"] for it in r["items"]}
        assert "000001" not in codes and "000002" not in codes, "QDII-商品/商品不应进 stock universe"

    def test_default_sort_ret_5y_desc(self, db_session):
        from src.db.models import FundPerformance
        import datetime
        db_session.add_all([
            _mk_fund("000001", market_subtype="股票型"),
            _mk_fund("000002", market_subtype="股票型"),
        ])
        db_session.add_all([
            FundPerformance(code="000001", as_of_date=datetime.date(2026, 9, 1), ret_5y=10.0),
            FundPerformance(code="000002", as_of_date=datetime.date(2026, 9, 1), ret_5y=30.0),
        ])
        db_session.commit()

        r = FilterService(db_session).screen_discovery_stock()
        assert r["items"][0]["code"] == "000002"
        assert r["items"][1]["code"] == "000001"

    def test_qdii_reits_excluded_when_qdii_coarse_unchecked(self, db_session):
        """回归：QDII-REITs 归 QDII 粗类别后，不勾 QDII 时必须排除（QDII-股票类同）。

        注：粗类别→精确 subtype 展开由前端 COARSE_TO_SUBTYPES_STOCK 完成，后端只认精确值。
        这里用前端展开后的精确列表调用 screen_discovery_stock，模拟真实请求。
        """
        db_session.add_all([
            _mk_fund("000001", market_subtype="QDII-REITs"),
            _mk_fund("000002", market_subtype="QDII-普通股票"),
            _mk_fund("000003", market_subtype="股票型"),
        ])
        db_session.commit()

        # 模拟前端展开：仅勾 REITs（不勾 QDII）→ ['Reits', 'REITs']
        r = FilterService(db_session).screen_discovery_stock(market_types=["Reits", "REITs"])
        codes = {it["code"] for it in r["items"]}
        assert codes == set(), f"QDII 基金不应出现，实际: {codes}"

        # 模拟前端展开：勾 QDII（不勾 REITs）→ QDII 系列 6 个精确 subtype
        qdii_subtypes = ['QDII-普通股票', 'QDII-混合偏股', 'QDII-混合灵活',
                         'QDII-混合平衡', 'QDII-FOF', 'QDII-REITs']
        r2 = FilterService(db_session).screen_discovery_stock(market_types=qdii_subtypes)
        codes2 = {it["code"] for it in r2["items"]}
        assert codes2 == {"000001", "000002"}

        # 模拟前端展开：同时勾 QDII + REITs → QDII 系列 + REITs 系列（股票型不在其中）
        all_subtypes = qdii_subtypes + ['Reits', 'REITs']
        r3 = FilterService(db_session).screen_discovery_stock(market_types=all_subtypes)
        codes3 = {it["code"] for it in r3["items"]}
        # 000003 market_subtype='股票型' 不在勾选列表里，不出现
        assert codes3 == {"000001", "000002"}


class TestUniverseStatsDiscovery:
    def test_bond_kind_counts_only_bond_universe(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="债券型-中短债"),
            _mk_fund("000002", market_subtype="指数型-固收"),
            _mk_fund("000003", market_subtype="股票型"),
        ])
        db_session.commit()

        r = FilterService(db_session).universe_stats("discovery-bond")
        assert r["total"] == 2

    def test_stock_kind_counts_only_stock_universe(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="股票型"),
            _mk_fund("000002", market_subtype="QDII-普通股票"),
            _mk_fund("000003", market_subtype="债券型-中短债"),
            _mk_fund("000004", market_subtype="FOF-稳健型"),
        ])
        db_session.commit()

        r = FilterService(db_session).universe_stats("discovery-stock")
        assert r["total"] == 2  # 仅 000001、000002

    def test_inactive_excluded_from_stats(self, db_session):
        db_session.add_all([
            _mk_fund("000001", market_subtype="债券型-中短债"),
            _mk_fund("000002", market_subtype="债券型-中短债", is_active=False),
        ])
        db_session.commit()

        r = FilterService(db_session).universe_stats("discovery-bond")
        assert r["total"] == 1


class TestRegressionExistingTabs:
    """回归：现有 bond/stock tab 行为不变"""

    def test_bond_screen_ignores_market_subtype(self, db_session, monkeypatch):
        """老 bond tab 不应被 market_subtype 字段干扰"""
        monkeypatch.setattr(
            "src.data.fund_universe.load_fund_codes",
            lambda *args, **kwargs: ["000001", "000002"],
        )
        db_session.add_all([
            _mk_fund("000001", market_subtype="债券型-长期纯债", fund_type="中长期纯债"),
            _mk_fund("000002", market_subtype="股票型", fund_type="股票型"),
            _mk_fund("000003", market_subtype="债券型-长期纯债", fund_type="中长期纯债"),
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


class TestDiscoveryPagination:
    """discovery-* tab 分页：total 仍是筛后总数，items 切片"""
    @staticmethod
    def _seed_many(db, n: int = 30, subtype: str = "债券型-长期纯债"):
        """seed N 只同 subtype，规模递增"""
        rows = [
            _mk_fund(f"{900000 + i}", market_subtype=subtype, size_yi=float(i + 1))
            for i in range(n)
        ]
        db.add_all(rows)
        db.commit()

    def test_discovery_bond_default_returns_all_when_under_limit(self, db_session):
        self._seed_many(db_session, n=5)
        r = FilterService(db_session).screen_discovery_bond(limit=50)
        assert r["total"] == 5
        assert len(r["items"]) == 5

    def test_discovery_bond_first_page_slice(self, db_session):
        self._seed_many(db_session, n=30)
        r = FilterService(db_session).screen_discovery_bond(
            sort="size_yi", order="desc", page=1, limit=10,
        )
        assert r["total"] == 30
        assert len(r["items"]) == 10
        sizes = [it["size_yi"] for it in r["items"]]
        assert sizes == [30.0, 29.0, 28.0, 27.0, 26.0, 25.0, 24.0, 23.0, 22.0, 21.0]

    def test_discovery_bond_second_page_no_overlap(self, db_session):
        self._seed_many(db_session, n=30)
        p1 = FilterService(db_session).screen_discovery_bond(
            sort="size_yi", order="desc", page=1, limit=10,
        )
        p2 = FilterService(db_session).screen_discovery_bond(
            sort="size_yi", order="desc", page=2, limit=10,
        )
        codes1 = {it["code"] for it in p1["items"]}
        codes2 = {it["code"] for it in p2["items"]}
        assert codes1.isdisjoint(codes2)
        sizes2 = [it["size_yi"] for it in p2["items"]]
        assert sizes2 == [20.0, 19.0, 18.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0, 11.0]
        assert p1["total"] == 30
        assert p2["total"] == 30

    def test_discovery_bond_oversized_page_returns_empty(self, db_session):
        self._seed_many(db_session, n=30)
        r = FilterService(db_session).screen_discovery_bond(
            sort="size_yi", order="desc", page=999, limit=10,
        )
        assert r["total"] == 30
        assert r["items"] == []

    def test_discovery_bond_total_unaffected_by_limit(self, db_session):
        self._seed_many(db_session, n=30)
        r = FilterService(db_session).screen_discovery_bond(
            sort="size_yi", order="desc", page=1, limit=5,
        )
        assert r["total"] == 30
        assert len(r["items"]) == 5

    def test_discovery_bond_none_sort_still_tail_with_pagination(self, db_session):
        # 5 只有 size_yi（valued）
        for i in range(5):
            code = f"{910000 + i}"
            db_session.add(_mk_fund(code, market_subtype="债券型-长期纯债",
                                    size_yi=float(10 - i)))
        # 3 只 size_yi=None
        for i in range(3):
            code = f"{920000 + i}"
            db_session.add(_mk_fund(code, market_subtype="债券型-长期纯债",
                                    size_yi=None))
        db_session.commit()
        r = FilterService(db_session).screen_discovery_bond(
            sort="size_yi", order="desc", page=1, limit=4,
        )
        assert r["total"] == 8
        assert [it["size_yi"] for it in r["items"]] == [10.0, 9.0, 8.0, 7.0]
        r2 = FilterService(db_session).screen_discovery_bond(
            sort="size_yi", order="desc", page=2, limit=4,
        )
        assert [it["size_yi"] for it in r2["items"]] == [6.0, None, None, None]

    def test_discovery_stock_first_page_slice(self, db_session):
        # 股基·市场
        from src.db.models import FundPerformance
        import datetime
        for i in range(30):
            code = f"{930000 + i}"
            db_session.add(_mk_fund(code, market_subtype="股票型",
                                    size_yi=float(i + 1)))
            db_session.add(FundPerformance(
                code=code, as_of_date=datetime.date(2026, 9, 1),
                ret_5y=float(100 - i),
            ))
        db_session.commit()
        r = FilterService(db_session).screen_discovery_stock(
            sort="ret_5y", order="desc", page=1, limit=10,
        )
        assert r["total"] == 30
        assert len(r["items"]) == 10
        rets = [it["ret_5y"] for it in r["items"]]
        assert rets == [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0]
        # 第 2 页 ret_5y = 90..81
        r2 = FilterService(db_session).screen_discovery_stock(
            sort="ret_5y", order="desc", page=2, limit=10,
        )
        assert [it["ret_5y"] for it in r2["items"]] == \
            [90.0, 89.0, 88.0, 87.0, 86.0, 85.0, 84.0, 83.0, 82.0, 81.0]
        assert r2["total"] == 30
