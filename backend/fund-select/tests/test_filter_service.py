"""
筛选逻辑单测：四维度组合 / 边界 / 排序 / LEFT JOIN 保留
"""
from src.services.filter_service import FilterService


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
