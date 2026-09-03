"""交叉泄漏回归：债基 / 股票宇宙按 yaml 代码集合隔离，不靠 fund_type。"""
from datetime import date

from src.db.models import Fund, FundFees, FundHoldingsBond, FundPerformance
from src.services.filter_service import FilterService


def _mk(code: str, **kw) -> Fund:
    defaults = dict(
        code=code, name=f"基金{code}", fund_type="债券型-长期纯债",
        age_years=5.0, size_yi=10.0,
        mgr_name="张", mgr_company="某司",
        mgr_days=2000, mgr_experience_years=5.5,
        is_active=True,
    )
    defaults.update(kw)
    return Fund(**defaults)


def _seed_mixed(db):
    """同一张表里混入债基宇宙、股票宇宙、两边都不在的活跃基金。"""
    db.add_all([
        _mk("100001", fund_type="债券型-长期纯债"),          # 债基 yaml
        _mk("100002", fund_type="混合型-偏债"),              # 债基 yaml（类型不是债）
        _mk("100003", fund_type="债券型-长期纯债", is_active=False),  # 债基 yaml 但清盘
        _mk("100004", fund_type="QDII"),                     # 债基 yaml
        _mk("200001", fund_type="股票型-标准指数"),          # 股票 yaml
        _mk("200002", fund_type="混合型-偏股"),              # 股票 yaml
        _mk("200003", fund_type="债券型-长期纯债"),          # 股票 yaml（类型是债，仍属股票宇宙）
        _mk("300001", fund_type="股票型-标准指数"),          # 两边 yaml 都没有
    ])
    db.add_all([
        FundPerformance(code="100001", as_of_date=date(2026, 9, 1), dd_3y=-2.0),
        FundPerformance(code="200001", as_of_date=date(2026, 9, 1), ret_5y=10.0),
        FundPerformance(code="200002", as_of_date=date(2026, 9, 1), ret_5y=8.0),
    ])
    db.add(FundFees(code="100001", fee_mgmt=0.3, fee_custody=0.1))
    db.add(FundHoldingsBond(
        code="100001", report_date=date(2025, 12, 31), rate_bond_pct=40.0,
    ))
    db.commit()


BOND_UNIVERSE = ["100001", "100002", "100003", "100004"]
STOCK_UNIVERSE = ["200001", "200002", "200003"]


def test_screen_does_not_leak_stock_or_outsiders(db_session):
    _seed_mixed(db_session)
    result = FilterService(db_session).screen(universe_codes=BOND_UNIVERSE)
    codes = {it["code"] for it in result["items"]}
    assert codes == {"100001", "100002", "100004"}
    assert "200001" not in codes
    assert "200002" not in codes
    assert "300001" not in codes
    assert "100003" not in codes  # 清盘


def test_screen_stock_does_not_leak_bond_or_outsiders(db_session):
    _seed_mixed(db_session)
    result = FilterService(db_session).screen_stock(universe_codes=STOCK_UNIVERSE)
    codes = {it["code"] for it in result["items"]}
    assert codes == {"200001", "200002", "200003"}
    assert "100001" not in codes
    assert "100002" not in codes
    assert "100004" not in codes
    assert "300001" not in codes


def test_bond_universe_keeps_mixed_and_qdii(db_session):
    _seed_mixed(db_session)
    result = FilterService(db_session).screen(universe_codes=BOND_UNIVERSE)
    codes = {it["code"] for it in result["items"]}
    assert "100002" in codes  # 混合型
    assert "100004" in codes  # QDII


def test_exclude_qdii_is_optional_overlay(db_session):
    """排除 QDII 是用户筛选，不是宇宙成员判定。默认仍保留 QDII。"""
    _seed_mixed(db_session)
    db_session.add_all([
        _mk("200004", fund_type="QDII-股票"),
        _mk("200005", fund_type="QDII-互认"),
        _mk("200006", fund_type="互认基金"),
        _mk("200007", fund_type=""),
    ])
    db_session.commit()
    svc = FilterService(db_session)

    bond_all = svc.screen(universe_codes=BOND_UNIVERSE)
    assert "100004" in {it["code"] for it in bond_all["items"]}

    bond = svc.screen(universe_codes=BOND_UNIVERSE, exclude_qdii=True)
    assert {it["code"] for it in bond["items"]} == {"100001", "100002"}

    stock_u = STOCK_UNIVERSE + ["200004", "200005", "200006", "200007"]
    stock = svc.screen_stock(universe_codes=stock_u, exclude_qdii=True)
    codes = {it["code"] for it in stock["items"]}
    assert codes == {"200001", "200002", "200003", "200007"}
    assert "200004" not in codes
    assert "200005" not in codes
    assert "200006" not in codes


def test_stock_universe_keeps_mixed_and_bond_typed(db_session):
    """成员判定不再看 fund_type：名单里的混合型、甚至债券型都留在股票 tab。"""
    _seed_mixed(db_session)
    result = FilterService(db_session).screen_stock(universe_codes=STOCK_UNIVERSE)
    codes = {it["code"] for it in result["items"]}
    assert "200002" in codes  # 混合型-偏股
    assert "200003" in codes  # 债券型，但在股票 yaml 里


def test_overlap_code_appears_in_both_universes(db_session):
    _seed_mixed(db_session)
    bond = FilterService(db_session).screen(universe_codes=["200001"])
    stock = FilterService(db_session).screen_stock(universe_codes=["200001"])
    assert {it["code"] for it in bond["items"]} == {"200001"}
    assert {it["code"] for it in stock["items"]} == {"200001"}


def test_get_detail_not_gated_by_universe(db_session):
    _seed_mixed(db_session)
    d = FilterService(db_session).get_detail("200001")
    assert d is not None
    assert d["code"] == "200001"


def test_universe_stats_counts_only_active_in_universe(db_session):
    _seed_mixed(db_session)
    svc = FilterService(db_session)
    bond = svc.universe_stats("bond", universe_codes=BOND_UNIVERSE)
    assert bond["total"] == 3  # 100001/100002/100004
    assert bond["with_performance"] == 1  # 100001
    assert bond["with_fees"] == 1
    assert bond["with_holdings"] == 1

    stock = svc.universe_stats("stock", universe_codes=STOCK_UNIVERSE)
    assert stock["total"] == 3
    assert stock["with_performance"] == 2  # 200001/200002
    assert stock["with_fees"] == 0
    assert stock["with_holdings"] == 0


def test_screen_follows_universe(db_session):
    """宇宙隔离（screen 层）：债基 screen 不含股票代码，反之亦然；exclude_qdii 生效"""
    _seed_mixed(db_session)
    svc = FilterService(db_session)

    bond = svc.screen(universe_codes=BOND_UNIVERSE, sort="size_yi", order="desc")
    codes = {it["code"] for it in bond["items"]}
    assert "100001" in codes
    assert "200001" not in codes

    stock = svc.screen_stock(universe_codes=STOCK_UNIVERSE, sort="ret_5y", order="desc")
    codes_s = {it["code"] for it in stock["items"]}
    assert "200001" in codes_s
    assert "100001" not in codes_s

    no_qdii = svc.screen(
        universe_codes=BOND_UNIVERSE, sort="size_yi", order="desc", exclude_qdii=True,
    )
    codes_n = {it["code"] for it in no_qdii["items"]}
    assert "100001" in codes_n
    assert "100004" not in codes_n
