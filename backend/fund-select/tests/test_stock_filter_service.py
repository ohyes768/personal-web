"""
screen_stock 单测：yaml 宇宙 ∩ is_active + 4 维度筛选 + 默认排序 ret_5y desc。
"""
from datetime import date

from src.db.models import Fund, FundPerformance, FundRiskMetrics
from src.services.filter_service import FilterService

STOCK_UNIVERSE = ["600001", "600002", "600003", "600004", "600005"]


def _mk_stock(code: str, **kw) -> Fund:
    defaults = dict(
        code=code, name=f"股票基{code}", fund_type="混合型-偏股",
        age_years=4.0, size_yi=10.0,
        mgr_name="张", mgr_company="某司",
        mgr_days=2000, mgr_experience_years=5.5,
        is_active=True,
    )
    defaults.update(kw)
    return Fund(**defaults)


def _seed_stock(db):
    db.add_all([
        # 宇宙内：股票型 / QDII / 混合型
        _mk_stock("600001", fund_type="股票型-标准指数"),
        _mk_stock("600002", fund_type="股票型-增强指数"),
        _mk_stock("600003", fund_type="QDII"),
        _mk_stock("600004", fund_type="QDII-股票"),
        _mk_stock("600005", fund_type="混合型-偏股"),
        # 库内但默认不在股票宇宙
        _mk_stock("600006", fund_type="债券型-长期纯债"),
        _mk_stock("600007", fund_type="股票型-标准指数", is_active=False),
        _mk_stock("600008", fund_type="QDII-债券"),
    ])
    # perf 给前 5 只（含混合型-偏股 600005）。600005 数值均匀居中。
    db.add_all([
        FundPerformance(code="600001", as_of_date=date(2026, 9, 1),
                        ret_5y=80.0, ret_1y=10.0, dd_3y=-15.0),
        FundPerformance(code="600002", as_of_date=date(2026, 9, 1),
                        ret_5y=60.0, ret_1y=8.0, dd_3y=-12.0),
        FundPerformance(code="600003", as_of_date=date(2026, 9, 1),
                        ret_5y=40.0, ret_1y=5.0, dd_3y=-10.0),
        FundPerformance(code="600004", as_of_date=date(2026, 9, 1),
                        ret_5y=20.0, ret_1y=3.0, dd_3y=-8.0),
        FundPerformance(code="600005", as_of_date=date(2026, 9, 1),
                        ret_5y=30.0, ret_1y=6.0, dd_3y=-7.0),
    ])
    db.commit()


def _screen_stock(db, **kw):
    kw.setdefault("universe_codes", STOCK_UNIVERSE)
    return FilterService(db).screen_stock(**kw)


def test_screen_stock_only_match(db_session):
    """只返回宇宙内且 is_active 的基金；名单外的债基/QDII-债券/清盘不出现。"""
    _seed_stock(db_session)
    result = _screen_stock(db_session)
    codes = {it["code"] for it in result["items"]}
    assert codes == {"600001", "600002", "600003", "600004", "600005"}
    assert result["total"] == 5
    assert "600006" not in codes
    assert "600007" not in codes
    assert "600008" not in codes


def test_screen_stock_default_sort_ret5y_desc(db_session):
    """默认 ret_5y desc：80 / 60 / 40 / 30 / 20"""
    _seed_stock(db_session)
    items = _screen_stock(db_session)["items"]
    # 600005 的 ret_5y=30 排在 600004(ret_5y=20) 之前
    assert [it["code"] for it in items] == [
        "600001", "600002", "600003", "600005", "600004"
    ]


def test_screen_stock_filters(db_session):
    """min_age/min_size_yi/max_dd_3y/min_mgr_exp 四维度同时应用"""
    _seed_stock(db_session)
    result = _screen_stock(
        db_session, min_age=3, min_size_yi=5, max_dd_3y=20, min_mgr_exp=5,
    )
    codes = {it["code"] for it in result["items"]}
    assert "600001" in codes
    assert len(codes) == 5


def test_screen_stock_max_dd_filters_out(db_session):
    """max_dd_3y=10 → 留下回撤>-10%（绝对值 ≤10），即 dd_3y >= -10
    600001(-15)/600002(-12) 没过；600003(-10)/600004(-8)/600005(-7) 过
    """
    _seed_stock(db_session)
    result = _screen_stock(db_session, max_dd_3y=10)
    codes = {it["code"] for it in result["items"]}
    assert codes == {"600003", "600004", "600005"}


def test_screen_stock_min_mgr_exp_filters_out(db_session):
    """min_mgr_exp=5.0：经理 4 年的 600010 即使在宇宙里也被筛掉。"""
    _seed_stock(db_session)
    db_session.merge(_mk_stock("600010", fund_type="股票型-标准指数",
                                mgr_experience_years=4.0))
    db_session.commit()
    result = _screen_stock(
        db_session, min_mgr_exp=5.0,
        universe_codes=STOCK_UNIVERSE + ["600010"],
    )
    codes = {it["code"] for it in result["items"]}
    assert "600010" not in codes
    assert "600001" in codes


def _seed_risk(db):
    """sharpe：1.2 / 0.8 / 0.5 / 无记录(600004) / 0.9"""
    db.add_all([
        FundRiskMetrics(code="600001", sharpe=1.2, as_of_date=date(2026, 9, 1)),
        FundRiskMetrics(code="600002", sharpe=0.8, as_of_date=date(2026, 9, 1)),
        FundRiskMetrics(code="600003", sharpe=0.5, as_of_date=date(2026, 9, 1)),
        FundRiskMetrics(code="600005", sharpe=0.9, as_of_date=date(2026, 9, 1)),
    ])
    db.commit()


def test_screen_stock_min_sharpe_filters_out(db_session):
    """min_sharpe=0.8：sharpe<0.8（600003）与无指标记录（600004）都被筛掉。"""
    _seed_stock(db_session)
    _seed_risk(db_session)
    result = _screen_stock(db_session, min_sharpe=0.8)
    codes = {it["code"] for it in result["items"]}
    assert codes == {"600001", "600002", "600005"}


def test_screen_stock_without_min_sharpe_keeps_null_metrics(db_session):
    """不传 min_sharpe：无风险指标的基金不受影响（行为不变）。"""
    _seed_stock(db_session)
    _seed_risk(db_session)
    result = _screen_stock(db_session)
    assert result["total"] == 5
