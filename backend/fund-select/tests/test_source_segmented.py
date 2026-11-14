"""
来源分段（11-15-source-segmented）单测：source=curated/market/all

覆盖：
- screen / screen_stock 的 curated 默认行为与旧 tab 逐字节一致
- market 走 akshare 子类圈定
- all 为 yaml ∪ 子类并集，in_curated 逐行标记正确
- universe_stats_sourced 三态计数一致（total(all) = |A∪M|）
- 非法 source 拒绝
- market_type（精确 subtype 白名单）在三种 source 下都生效
"""
import pytest

from src.services.filter_service import FilterService

BOND_SUBTYPE = "债券型-长债"     # ∈ DISCOVERY_BOND_SUBTYPES（akshare 原值）
BOND_SUBTYPE_2 = "债券型-中短债"  # ∈ DISCOVERY_BOND_SUBTYPES（另一个纯债子类）
STOCK_SUBTYPE = "混合型-偏股"        # ∈ DISCOVERY_STOCK_SUBTYPES


@pytest.fixture
def sourced_db(db_session, monkeypatch):
    """名单内/名单外/市场独有三类基金（yaml 名单 mock 为 000001、000002）。

    000001 三分法 A：yaml ∈ 名单，子类 ∈ 债券 universe → 三处都在
    000002 三分法 B：yaml ∈ 名单，子类不在 discovery universe → 仅 curated
    000010 市场独有 M：不在 yaml，子类 ∈ universe → 仅 market
    000011 无子类 N：不在 yaml，market_subtype=None → 三处都不可见（市场判定排除）
    """
    from src.db.models import Fund, FundPerformance
    from datetime import date

    def _load(config_path=None):
        return ["000001", "000002"]

    monkeypatch.setattr("src.data.fund_universe.load_fund_codes", _load)
    db_session.add_all([
        Fund(code="000001", name="名单内", market_subtype=BOND_SUBTYPE,
             age_years=5.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
        Fund(code="000002", name="名单内非市场子类", market_subtype="其他另类策略",
             age_years=5.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
        Fund(code="000010", name="市场独有", market_subtype=BOND_SUBTYPE,
             age_years=5.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
        Fund(code="000011", name="无子类", market_subtype=None,
             age_years=5.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
    ])
    db_session.add_all([
        FundPerformance(code=c, as_of_date=date(2026, 9, 1), dd_3y=-3.0,
                        ret_1y=2.0, ret_3y=8.0, ret_5y=20.0)
        for c in ("000001", "000002", "000010", "000011")
    ])
    db_session.commit()
    return db_session


class TestScreenSources:
    def test_default_is_curated(self, sourced_db):
        """不传 source：行为 = 旧债基 tab（yaml 名单）"""
        r = FilterService(sourced_db).screen()
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002"}
        assert all(it["in_curated"] for it in r["items"])
        assert r["source"] == "curated"

    def test_explicit_curated_same(self, sourced_db):
        r = FilterService(sourced_db).screen(source="curated")
        assert {it["code"] for it in r["items"]} == {"000001", "000002"}

    def test_market_excludes_yaml_only(self, sourced_db):
        """market：只看子类圈定；名单内但子类不在 universe 的 000002 不出现。

        000001 名单 ∩ 子类两处都在 → in_curated=True（徽章照常显示名单成员）
        """
        r = FilterService(sourced_db).screen(source="market")
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000010"}
        marked = {it["code"]: it["in_curated"] for it in r["items"]}
        assert marked == {"000001": True, "000010": False}

    def test_all_is_union(self, sourced_db):
        """all：yaml ∪ 子类；含名单独有（000002）与市场独有（000010）"""
        r = FilterService(sourced_db).screen(source="all")
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002", "000010"}
        marked = {it["code"]: it["in_curated"] for it in r["items"]}
        assert marked == {"000001": True, "000002": True, "000010": False}

    def test_all_inactive_excluded(self, sourced_db):
        """并集仍遵守 is_active"""
        from src.db.models import Fund
        sourced_db.get(Fund, "000010").is_active = False
        sourced_db.commit()
        r = FilterService(sourced_db).screen(source="all")
        assert "000010" not in {it["code"] for it in r["items"]}

    def test_invalid_source_rejected(self, sourced_db):
        with pytest.raises(ValueError):
            FilterService(sourced_db).screen(source="bogus")

    def test_market_only_fund_detail_filters(self, sourced_db):
        """market/all 态下旧筛选条件照常生效"""
        r = FilterService(sourced_db).screen(source="all", min_age=6.0)
        assert r["total"] == 0


class TestScreenStockSources:
    def test_stock_all_union(self, sourced_db):
        """股基并集：子类走 DISCOVERY_STOCK_SUBTYPES"""
        from src.db.models import Fund
        sourced_db.add(Fund(code="000020", name="市场股基", market_subtype=STOCK_SUBTYPE,
                            age_years=5.0, size_yi=10.0, mgr_experience_years=8.0,
                            is_active=True))
        sourced_db.commit()
        r = FilterService(sourced_db).screen_stock(source="all")
        codes = {it["code"] for it in r["items"]}
        assert codes == {"000001", "000002", "000020"}
        assert all(it["in_curated"] for it in r["items"] if it["code"] != "000020")


class TestUniverseStatsSourced:
    def test_stats_three_states(self, sourced_db):
        svc = FilterService(sourced_db)
        curated = svc.universe_stats_sourced("bond", "discovery-bond", "curated")
        market = svc.universe_stats_sourced("bond", "discovery-bond", "market")
        all_ = svc.universe_stats_sourced("bond", "discovery-bond", "all")
        assert curated["total"] == 2
        assert market["total"] == 2          # 000001 + 000010
        assert all_["total"] == 3            # yaml(2) ∪ market(2) - 交集(1)
        assert all_["with_performance"] == 3

    def test_stats_invalid_source(self, sourced_db):
        with pytest.raises(ValueError):
            FilterService(sourced_db).universe_stats_sourced("bond", "discovery-bond", "x")


class TestSubtypeUniverse:
    """SUBCLASS_TO_CATEGORY 的键必须是 akshare 基金类型列的**原值**。

    历史事故：键写成「债券型-长期纯债」，而 akshare 原值是「债券型-长债」——
    生产库 2653 只长债全部降级 other，混不进债基 universe，债基·市场少了一大片。
    """

    def test_long_bond_subtype_in_bond_universe(self):
        from src.data.market_subtype_map import (
            DISCOVERY_BOND_SUBTYPES, SUBCLASS_TO_CATEGORY,
        )
        assert "债券型-长债" in DISCOVERY_BOND_SUBTYPES
        assert SUBCLASS_TO_CATEGORY["债券型-长债"] == "bond"

    def test_every_declared_subtype_is_reachable_from_ui_mapping(self):
        """契约 §8a：后端 universe 与前端粗类别表必须一一对应（不漏不多）。"""
        from src.data.market_subtype_map import (
            DISCOVERY_BOND_SUBTYPES, DISCOVERY_STOCK_SUBTYPES,
        )
        import sys
        from pathlib import Path
        import re

        ts = (Path(__file__).resolve().parents[3]
              / "apps" / "fund-select" / "src" / "lib" / "types.ts")
        if not ts.exists():          # 单测可脱离前端仓库运行
            pytest.skip("前端 types.ts 不在测试环境")
        src = ts.read_text(encoding="utf-8")

        def _ui_subtypes(block: str) -> set[str]:
            m = re.search(re.escape(block) + r"[^=]*=\s*\{(.*?)\};", src, re.S)
            assert m, f"前端找不到 {block}"
            return set(re.findall(r"'([^']+)'", m.group(1)))

        ui_bond = _ui_subtypes("COARSE_TO_SUBTYPES_BOND")
        ui_stock = _ui_subtypes("COARSE_TO_SUBTYPES_STOCK")
        # 前端表允许比后端 universe 多（覆盖历史子类），但不能少
        missing_bond = set(DISCOVERY_BOND_SUBTYPES) - ui_bond
        missing_stock = set(DISCOVERY_STOCK_SUBTYPES) - ui_stock
        assert not missing_bond, f"前端债基粗类别表漏了 {missing_bond}"
        assert not missing_stock, f"前端股基粗类别表漏了 {missing_stock}"


class TestMarketTypeFilter:
    """market_type（精确 subtype 白名单）在三种 source 下都生效。

    前端 UI 选的是粗类别，展开成精确 subtype 后以 CSV 传进来；后端不再
    把它当 universe（universe 由 source 决定），而是额外的 WHERE 条件。
    """

    @pytest.fixture
    def typed_db(self, sourced_db):
        from src.db.models import Fund
        sourced_db.add(Fund(code="000012", name="中短债", market_subtype=BOND_SUBTYPE_2,
                            age_years=5.0, size_yi=10.0, mgr_experience_years=8.0,
                            is_active=True))
        sourced_db.commit()
        return sourced_db

    def test_market_filters_by_subtype(self, typed_db):
        r = FilterService(typed_db).screen(source="market", market_types=[BOND_SUBTYPE_2])
        assert {it["code"] for it in r["items"]} == {"000012"}

    def test_curated_filters_by_subtype(self, typed_db):
        """三分法态：只保留名单里子类命中白名单的那只（000001=长债 命中，000002=其他 被剔除）"""
        r = FilterService(typed_db).screen(source="curated", market_types=[BOND_SUBTYPE])
        assert {it["code"] for it in r["items"]} == {"000001"}

    def test_all_filters_by_subtype(self, typed_db):
        r = FilterService(typed_db).screen(source="all", market_types=[BOND_SUBTYPE_2])
        assert {it["code"] for it in r["items"]} == {"000012"}

    def test_no_market_type_means_no_restriction(self, typed_db):
        r = FilterService(typed_db).screen(source="market", market_types=None)
        assert {it["code"] for it in r["items"]} == {"000001", "000010", "000012"}

    def test_market_type_outside_universe_returns_empty(self, typed_db):
        """白名单里全是不在 universe 的子类 → 空集（不报错）"""
        r = FilterService(typed_db).screen(source="market", market_types=["货币型-普通货币"])
        assert r["total"] == 0

    def test_stock_side_market_type(self, typed_db):
        from src.db.models import Fund
        typed_db.add(Fund(code="000020", name="股基", market_subtype=STOCK_SUBTYPE,
                          age_years=5.0, size_yi=10.0, mgr_experience_years=8.0,
                          is_active=True))
        typed_db.commit()
        r = FilterService(typed_db).screen_stock(source="market", market_types=[STOCK_SUBTYPE])
        assert {it["code"] for it in r["items"]} == {"000020"}
        r2 = FilterService(typed_db).screen_stock(source="market", market_types=[BOND_SUBTYPE])
        assert {it["code"] for it in r2["items"]} == set()
