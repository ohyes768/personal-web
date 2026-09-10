"""
筛选逻辑单测：四维度组合 / 边界 / 排序 / LEFT JOIN 保留
"""
from src.services.filter_service import FilterService, _parse_peer_rank


class TestScreen:
    def test_no_filter_returns_active_only(self, seeded_db):
        """无参数：返回全部 is_active（C 被排除，D 无业绩也保留）"""
        r = FilterService(seeded_db).screen()
        codes = [it["code"] for it in r["items"]]
        assert r["total"] == 3
        assert "000003" not in codes   # is_active=False
        assert "000004" in codes       # 无业绩 LEFT JOIN 保留

    def test_min_age(self, seeded_db):
        r = FilterService(seeded_db).screen(min_age=3)
        assert [it["code"] for it in r["items"]] == ["000001", "000004"]  # B=1年被排除

    def test_min_size(self, seeded_db):
        r = FilterService(seeded_db).screen(min_size_yi=1.0)
        assert {it["code"] for it in r["items"]} == {"000001", "000004"}

    def test_max_dd_3y_uses_absolute_value(self, seeded_db):
        """库内 dd_3y 为负值；阈值 5 应保留 -3.0 排除 -8.0"""
        r = FilterService(seeded_db).screen(max_dd_3y=5)
        assert "000001" in [it["code"] for it in r["items"]]
        assert "000002" not in [it["code"] for it in r["items"]]

    def test_min_mgr_exp(self, seeded_db):
        r = FilterService(seeded_db).screen(min_mgr_exp=5)
        assert "000002" not in [it["code"] for it in r["items"]]

    def test_combined_filters(self, seeded_db):
        """四维组合"""
        r = FilterService(seeded_db).screen(min_age=3, min_size_yi=1, max_dd_3y=5, min_mgr_exp=5)
        assert [it["code"] for it in r["items"]] == ["000001"]

    def test_default_sort_size_desc(self, seeded_db):
        r = FilterService(seeded_db).screen()
        sizes = [it["size_yi"] for it in r["items"]]
        assert sizes == sorted(sizes, reverse=True)

    def test_sort_dd_3y_asc_optimal_first(self, seeded_db):
        """回撤 asc：绝对值小（优）在前，None 最后"""
        r = FilterService(seeded_db).screen(sort="dd_3y", order="asc")
        codes = [it["code"] for it in r["items"]]
        assert codes[0] == "000001"      # |-3| < |-8|
        assert codes[-1] == "000004"     # None 排最后


class TestFeeAnnual:
    def test_fee_annual_mgm_custody(self, seeded_db):
        items = {it["code"]: it for it in FilterService(seeded_db).screen()["items"]}
        assert items["000001"]["fee_annual"] == 0.4        # 0.3 + 0.1
        assert items["000002"]["fee_annual"] == 1.05       # 0.5 + 0.15 + 0.4
        assert items["000004"]["fee_annual"] is None       # 无费率记录


class TestDetail:
    def test_get_detail_found(self, seeded_db):
        d = FilterService(seeded_db).get_detail("000001")
        assert d["code"] == "000001"
        assert d["fees"]["fee_mgmt"] == 0.3
        assert d["holdings"]["rate_bond_pct"] == 30.0

    def test_get_detail_no_holdings(self, seeded_db):
        d = FilterService(seeded_db).get_detail("000004")
        assert d["holdings"] is None
        assert d["ret_3y"] is None

    def test_get_detail_not_found(self, seeded_db):
        assert FilterService(seeded_db).get_detail("999999") is None

    def test_get_detail_includes_risk_metrics(self, seeded_db):
        """有 FundRiskMetrics 行时，详情接口返回 sharpe/ir/alpha/gamma/alpha_ir/excess_3y（用于 Hero 区 RiskMetricsGrid）"""
        from datetime import date

        from src.db.models import FundRiskMetrics

        seeded_db.add(FundRiskMetrics(
            code="000001",
            sharpe=1.5, ir=0.8, alpha=0.05, gamma=0.02, alpha_ir=1.2, excess_3y=0.15,
            as_of_date=date(2026, 9, 1),
        ))
        seeded_db.commit()

        d = FilterService(seeded_db).get_detail("000001")
        assert d["sharpe"] == 1.5
        assert d["ir"] == 0.8
        assert d["alpha"] == 0.05
        assert d["gamma"] == 0.02
        assert d["alpha_ir"] == 1.2
        assert d["excess_3y"] == 0.15

    def test_get_detail_risk_metrics_none_when_missing(self, seeded_db):
        """无 FundRiskMetrics 行时（LEFT JOIN 缺失），risk 字段全为 None（前端显示「无数据」）"""
        d = FilterService(seeded_db).get_detail("000004")
        assert d["sharpe"] is None
        assert d["ir"] is None
        assert d["alpha"] is None
        assert d["gamma"] is None
        assert d["alpha_ir"] is None
        assert d["excess_3y"] is None


class TestParsePeerRank:
    """雪球 peer_rank='1694/5606' → pct/total 字典；格式异常统一 None。"""

    def test_valid(self):
        assert _parse_peer_rank("1694/5606") == {"pct": 30.2, "total": 5606, "rank": 1694}

    def test_valid_leading_one(self):
        # 最强基金：1/N
        assert _parse_peer_rank("1/5615") == {"pct": 0.0, "total": 5615, "rank": 1}

    def test_invalid_formats_return_none(self):
        for v in ("abc", "1", "", "1/0", "-1/5", "5/3", "1//2", " /5", "1/ "):
            assert _parse_peer_rank(v) is None, f"expected None for {v!r}"

    def test_none_input(self):
        assert _parse_peer_rank(None) is None

    def test_whitespace_tolerated(self):
        assert _parse_peer_rank("  100  /  500  ") == {"pct": 20.0, "total": 500, "rank": 100}


class TestPagination:
    """分页（page/limit）：total 仍是筛后总数，items 切片"""
    @staticmethod
    def _seed_many(db, n: int = 30, monkeypatch=None):
        """seed N 只活跃债基，规模按序号递增，便于排序断言。
        同时 monkeypatch load_fund_codes 让 universe 包含这些 code。
        """
        from src.db.models import Fund
        rows = []
        codes = []
        for i in range(n):
            code = f"{i + 10:06d}"
            codes.append(code)
            rows.append(Fund(
                code=code, name=f"基金{code}", fund_type="债券型-长期纯债",
                age_years=5.0, size_yi=float(i + 1),  # 1..30
                mgr_name="张", mgr_company="某司",
                mgr_days=3650, mgr_experience_years=10.0, is_active=True,
            ))
        db.add_all(rows)
        db.commit()
        if monkeypatch is not None:
            monkeypatch.setattr(
                "src.data.fund_universe.load_fund_codes",
                lambda *args, **kwargs: codes,
            )
        return codes

    def test_default_returns_all_when_under_limit(self, db_session, monkeypatch):
        self._seed_many(db_session, n=5, monkeypatch=monkeypatch)
        r = FilterService(db_session).screen(limit=50)
        assert r["total"] == 5
        assert len(r["items"]) == 5

    def test_first_page_slice(self, db_session, monkeypatch):
        self._seed_many(db_session, n=30, monkeypatch=monkeypatch)
        r = FilterService(db_session).screen(sort="size_yi", order="desc", page=1, limit=10)
        assert r["total"] == 30
        assert len(r["items"]) == 10
        # size_yi desc：前 10 名 size=30..21
        sizes = [it["size_yi"] for it in r["items"]]
        assert sizes == [30.0, 29.0, 28.0, 27.0, 26.0, 25.0, 24.0, 23.0, 22.0, 21.0]

    def test_second_page_no_overlap(self, db_session, monkeypatch):
        self._seed_many(db_session, n=30, monkeypatch=monkeypatch)
        p1 = FilterService(db_session).screen(sort="size_yi", order="desc", page=1, limit=10)
        p2 = FilterService(db_session).screen(sort="size_yi", order="desc", page=2, limit=10)
        codes1 = {it["code"] for it in p1["items"]}
        codes2 = {it["code"] for it in p2["items"]}
        assert codes1.isdisjoint(codes2)
        # 第 2 页 size=20..11
        sizes2 = [it["size_yi"] for it in p2["items"]]
        assert sizes2 == [20.0, 19.0, 18.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0, 11.0]
        # total 与 page 无关
        assert p1["total"] == 30
        assert p2["total"] == 30

    def test_oversized_page_returns_empty(self, db_session, monkeypatch):
        self._seed_many(db_session, n=30, monkeypatch=monkeypatch)
        r = FilterService(db_session).screen(sort="size_yi", order="desc", page=999, limit=10)
        assert r["total"] == 30
        assert r["items"] == []

    def test_total_unaffected_by_limit(self, db_session, monkeypatch):
        self._seed_many(db_session, n=30, monkeypatch=monkeypatch)
        r = FilterService(db_session).screen(sort="size_yi", order="desc", page=1, limit=5)
        assert r["total"] == 30
        assert len(r["items"]) == 5

    def test_none_sort_still_tail_with_pagination(self, db_session, monkeypatch):
        """None 值仍排末位；分页切片不破坏顺序"""
        from src.db.models import Fund
        codes = []
        # 5 只有 size_yi（valued）
        for i in range(5):
            code = f"{i + 10:06d}"
            codes.append(code)
            db_session.add(Fund(
                code=code, name=f"基金{code}", fund_type="债券型",
                age_years=5.0, size_yi=float(10 - i),  # 10,9,8,7,6
                mgr_name="x", mgr_company="y", mgr_days=100, mgr_experience_years=1.0,
                is_active=True))
        # 3 只 size_yi=None（empty，固定排末位）
        for i in range(3):
            code = f"{i + 20:06d}"
            codes.append(code)
            db_session.add(Fund(
                code=code, name=f"空基金{i}", fund_type="债券型",
                age_years=5.0, size_yi=None,
                mgr_name="x", mgr_company="y", mgr_days=100, mgr_experience_years=1.0,
                is_active=True))
        db_session.commit()
        monkeypatch.setattr(
            "src.data.fund_universe.load_fund_codes",
            lambda *args, **kwargs: codes,
        )
        r = FilterService(db_session).screen(sort="size_yi", order="desc", page=1, limit=4)
        assert r["total"] == 8
        # 前 4 名是 valued 段（10,9,8,7）
        assert [it["size_yi"] for it in r["items"]] == [10.0, 9.0, 8.0, 7.0]
        # 第 2 页：第 5 名 + 3 个 empty（None 排末位）
        r2 = FilterService(db_session).screen(sort="size_yi", order="desc", page=2, limit=4)
        assert [it["size_yi"] for it in r2["items"]] == [6.0, None, None, None]
