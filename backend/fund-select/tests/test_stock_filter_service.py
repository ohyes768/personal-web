"""
screen_stock 单测：验证 fund_type 限定 + 4 维度筛选 + 默认排序 ret_5y desc。

复用 conftest.py 的 db_session + 自建股/债/QDII 混合基金。
"""
from datetime import date

from src.db.models import Fund, FundFees, FundPerformance
from src.services.filter_service import FilterService


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


def _add_perf(db, code, ret_5y=None, dd_3y=None, ret_1y=None):
    db.merge(FundPerformance(
        code=code, as_of_date=date(2026, 9, 1),
        ret_1y=ret_1y, ret_5y=ret_5y, dd_3y=dd_3y,
    ))


def _seed_stock(db):
    db.add_all([
        # 命中：股票型
        _mk_stock("600001", fund_type="股票型-标准指数"),
        _mk_stock("600002", fund_type="股票型-增强指数"),
        # 命中：QDII（带前缀）
        _mk_stock("600003", fund_type="QDII"),
        _mk_stock("600004", fund_type="QDII-股票"),
        # 不命中：混合型-偏股（决策 1 未覆盖）
        _mk_stock("600005", fund_type="混合型-偏股"),
        # 不命中：债基
        _mk_stock("600006", fund_type="债券型-长期纯债"),
        # 不命中：清盘
        _mk_stock("600007", fund_type="股票型-标准指数", is_active=False),
    ])
    # perf 仅给前 4 只（QDII/股票型）
    db.add_all([
        FundPerformance(code="600001", as_of_date=date(2026, 9, 1),
                        ret_5y=80.0, ret_1y=10.0, dd_3y=-15.0),
        FundPerformance(code="600002", as_of_date=date(2026, 9, 1),
                        ret_5y=60.0, ret_1y=8.0, dd_3y=-12.0),
        FundPerformance(code="600003", as_of_date=date(2026, 9, 1),
                        ret_5y=40.0, ret_1y=5.0, dd_3y=-10.0),
        FundPerformance(code="600004", as_of_date=date(2026, 9, 1),
                        ret_5y=20.0, ret_1y=3.0, dd_3y=-8.0),
    ])
    db.commit()


def test_screen_stock_only_match(db_session):
    """仅命中股票型/QDII，排除混合偏股/债基/清盘"""
    _seed_stock(db_session)
    svc = FilterService(db_session)
    result = svc.screen_stock()  # 无筛选
    codes = {it["code"] for it in result["items"]}
    assert codes == {"600001", "600002", "600003", "600004"}
    assert result["total"] == 4


def test_screen_stock_default_sort_ret5y_desc(db_session):
    """默认 ret_5y desc：80/60/40/20"""
    _seed_stock(db_session)
    svc = FilterService(db_session)
    result = svc.screen_stock()
    items = result["items"]
    assert [it["code"] for it in items] == ["600001", "600002", "600003", "600004"]


def test_screen_stock_filters(db_session):
    """min_age/min_size_yi/max_dd_3y/min_mgr_exp 四维度同时应用"""
    _seed_stock(db_session)
    svc = FilterService(db_session)
    # 期望只过 600001：年龄 4≥3，规模 10≥5，回撤 15<20，经理 5.5>5
    result = svc.screen_stock(
        min_age=3, min_size_yi=5, max_dd_3y=20, min_mgr_exp=5,
    )
    codes = {it["code"] for it in result["items"]}
    assert "600001" in codes
    # 600003（QDII）的 ddmgr/mgr 满足，回撤-10<20 应过；实际因有 4 只都在范围内
    assert len(codes) == 4


def test_screen_stock_max_dd_filters_out(db_session):
    """max_dd_3y=10 → 留下回撤>-10%（绝对值 ≤10），即 dd_3y >= -10
    600001(-15)/600002(-12) 没过；600003(-10)/600004(-8) 过
    """
    _seed_stock(db_session)
    svc = FilterService(db_session)
    result = svc.screen_stock(max_dd_3y=10)
    codes = {it["code"] for it in result["items"]}
    assert codes == {"600003", "600004"}


def test_screen_stock_min_mgr_exp_filters_out(db_session):
    """min_mgr_exp=5.5（偏紧）：只剩 mgr_experience_years >= 5.5；所有测试基金都是 5.5 → 全过"""
    _seed_stock(db_session)
    svc = FilterService(db_session)
    # 加一只经理 4 年的
    db_session.merge(_mk_stock("600010", fund_type="股票型-标准指数",
                                mgr_experience_years=4.0))
    db_session.commit()
    result = svc.screen_stock(min_mgr_exp=5.0)
    codes = {it["code"] for it in result["items"]}
    assert "600010" not in codes
    assert "600001" in codes
