"""
screen_stock 单测：yaml 宇宙 ∩ is_active + 4 维度筛选 + 默认排序 ret_5y desc。
"""
from datetime import date

from src.db.models import Fund, FundAchievementRank, FundPerformance, FundRiskMetrics
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


def _seed_ranks_full(db, codes):
    """4 个目标周期全部入库；4 段位分别为顶部 5% / 20% / 60% / 90%。"""
    targets = [
        ("年度业绩", "今年以来"),
        ("阶段业绩", "近1年"),
        ("阶段业绩", "近3年"),
        ("阶段业绩", "近5年"),
    ]
    ranks = ("50", "200", "600", "900")  # /1000
    total = "1000"
    rows = []
    for code in codes:
        for i, (pk, pp) in enumerate(targets):
            rows.append(FundAchievementRank(
                code=code, period_kind=pk, period=pp,
                peer_rank=f"{ranks[i]}/{total}",
                as_of_date=date(2026, 9, 1),
            ))
    db.add_all(rows)
    db.commit()


def test_screen_stock_dto_has_rank_keys_with_full_data(db_session):
    """完整排名数据 → 4 个 rank 字段均有值"""
    _seed_stock(db_session)
    _seed_ranks_full(db_session, ["600001", "600002"])
    items = _screen_stock(db_session)["items"]
    for it in items:
        assert set(["rank_ytd", "rank_1y", "rank_3y", "rank_5y"]).issubset(it.keys())
    by_code = {it["code"]: it for it in items}
    assert by_code["600001"]["rank_ytd"] == {"pct": 5.0, "total": 1000}
    assert by_code["600001"]["rank_1y"] == {"pct": 20.0, "total": 1000}
    assert by_code["600001"]["rank_3y"] == {"pct": 60.0, "total": 1000}
    assert by_code["600001"]["rank_5y"] == {"pct": 90.0, "total": 1000}


def test_screen_stock_dto_rank_null_when_no_data(db_session):
    """完全无排名数据 → 4 个 rank 字段均为 None，不报错"""
    _seed_stock(db_session)
    items = _screen_stock(db_session)["items"]
    for it in items:
        assert it["rank_ytd"] is None
        assert it["rank_1y"] is None
        assert it["rank_3y"] is None
        assert it["rank_5y"] is None


def test_screen_stock_dto_rank_partial(db_session):
    """部分周期有数据 → 该键为 pct dict，缺的为 None"""
    _seed_stock(db_session)
    db_session.add(FundAchievementRank(
        code="600001", period_kind="阶段业绩", period="近1年",
        peer_rank="100/1000", as_of_date=date(2026, 9, 1),
    ))
    db_session.add(FundAchievementRank(
        code="600001", period_kind="阶段业绩", period="近5年",
        peer_rank="abc",  # 异常格式
        as_of_date=date(2026, 9, 1),
    ))
    db_session.commit()
    items = {it["code"]: it for it in _screen_stock(db_session)["items"]}
    assert items["600001"]["rank_1y"] == {"pct": 10.0, "total": 1000}
    assert items["600001"]["rank_5y"] is None      # 异常格式
    assert items["600001"]["rank_ytd"] is None    # 完全无记录
    assert items["600001"]["rank_3y"] is None
    # 其余基金一律 None
    for code in ("600002", "600003", "600004", "600005"):
        assert items[code]["rank_ytd"] is None
        assert items[code]["rank_1y"] is None


def test_screen_stock_dto_unrelated_period_ignored(db_session):
    """入库了非目标周期的排名 → 不出现在 DTO 4 字段"""
    _seed_stock(db_session)
    db_session.add(FundAchievementRank(
        code="600001", period_kind="阶段业绩", period="近1月",
        peer_rank="10/1000", as_of_date=date(2026, 9, 1),
    ))
    db_session.add(FundAchievementRank(
        code="600001", period_kind="年度业绩", period="2024",
        peer_rank="100/5000", as_of_date=date(2026, 9, 1),
    ))
    db_session.commit()
    items = {it["code"]: it for it in _screen_stock(db_session)["items"]}
    # 4 个目标键一律 None，不被"近1月"或"2024"污染
    for k in ("rank_ytd", "rank_1y", "rank_3y", "rank_5y"):
        assert items["600001"][k] is None


def test_screen_bond_dto_has_rank_keys_all_null(seeded_db):
    """债基 tab 永远返回 4 个 rank 键但全 None（接口契约向后兼容）"""
    items = FilterService(seeded_db).screen()["items"]
    for it in items:
        assert set(["rank_ytd", "rank_1y", "rank_3y", "rank_5y"]).issubset(it.keys())
        assert it["rank_ytd"] is None
        assert it["rank_1y"] is None
        assert it["rank_3y"] is None
        assert it["rank_5y"] is None


class TestStockPagination:
    """stock tab 分页：total 仍是筛后总数，items 切片"""
    @staticmethod
    def _seed_many_stock(db, n: int = 30):
        db.add_all([
            _mk_stock(f"{700000 + i}", fund_type="股票型-标准指数",
                      size_yi=float(i + 1))  # 1..30
            for i in range(n)
        ])
        db.add_all([
            FundPerformance(code=f"{700000 + i}", as_of_date=date(2026, 9, 1),
                            ret_5y=float(100 - i),  # 100,99,..71
                            ret_1y=5.0, dd_3y=-10.0)
            for i in range(n)
        ])
        # 把股票 universe 扩到全部 30 只
        new_universe = STOCK_UNIVERSE + [f"{700000 + i}" for i in range(n)]
        db.commit()
        return new_universe

    def test_default_returns_all_when_under_limit(self, db_session):
        # 已有 5 只 + 1 只新，规模递增
        _seed_stock(db_session)
        r = _screen_stock(db_session, limit=50)
        assert r["total"] == 5
        assert len(r["items"]) == 5

    def test_first_page_slice(self, db_session):
        new_universe = self._seed_many_stock(db_session, n=30)
        r = _screen_stock(db_session, sort="ret_5y", order="desc",
                          universe_codes=new_universe, page=1, limit=10)
        assert r["total"] == 30
        assert len(r["items"]) == 10
        # ret_5y desc：100,99,..,91
        rets = [it["ret_5y"] for it in r["items"]]
        assert rets == [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0]

    def test_second_page_no_overlap(self, db_session):
        new_universe = self._seed_many_stock(db_session, n=30)
        p1 = _screen_stock(db_session, sort="ret_5y", order="desc",
                           universe_codes=new_universe, page=1, limit=10)
        p2 = _screen_stock(db_session, sort="ret_5y", order="desc",
                           universe_codes=new_universe, page=2, limit=10)
        codes1 = {it["code"] for it in p1["items"]}
        codes2 = {it["code"] for it in p2["items"]}
        assert codes1.isdisjoint(codes2)
        # 第 2 页 ret_5y = 90..81
        rets2 = [it["ret_5y"] for it in p2["items"]]
        assert rets2 == [90.0, 89.0, 88.0, 87.0, 86.0, 85.0, 84.0, 83.0, 82.0, 81.0]
        assert p1["total"] == 30
        assert p2["total"] == 30

    def test_oversized_page_returns_empty(self, db_session):
        new_universe = self._seed_many_stock(db_session, n=30)
        r = _screen_stock(db_session, sort="ret_5y", order="desc",
                          universe_codes=new_universe, page=999, limit=10)
        assert r["total"] == 30
        assert r["items"] == []

    def test_total_unaffected_by_limit(self, db_session):
        new_universe = self._seed_many_stock(db_session, n=30)
        r = _screen_stock(db_session, sort="ret_5y", order="desc",
                          universe_codes=new_universe, page=1, limit=5)
        assert r["total"] == 30
        assert len(r["items"]) == 5

    def test_none_sort_still_tail_with_pagination(self, db_session):
        """ret_5y=None 仍排末位；分页切片不破坏顺序"""
        from src.db.models import Fund as _Fund
        # 5 只有 ret_5y
        for i in range(5):
            code = f"{710000 + i}"
            db_session.add(_mk_stock(code, fund_type="股票型-标准指数",
                                     size_yi=10.0))
            db_session.add(FundPerformance(code=code, as_of_date=date(2026, 9, 1),
                                           ret_5y=float(10 - i)))  # 10,9,8,7,6
        # 3 只 ret_5y=None
        for i in range(3):
            code = f"{720000 + i}"
            db_session.add(_mk_stock(code, fund_type="股票型-标准指数",
                                     size_yi=10.0))
            db_session.add(FundPerformance(code=code, as_of_date=date(2026, 9, 1),
                                           ret_5y=None))
        db_session.commit()
        new_universe = STOCK_UNIVERSE + \
            [f"{710000 + i}" for i in range(5)] + \
            [f"{720000 + i}" for i in range(3)]
        r = _screen_stock(db_session, sort="ret_5y", order="desc",
                          universe_codes=new_universe, page=1, limit=4)
        assert r["total"] == 8
        assert [it["ret_5y"] for it in r["items"]] == [10.0, 9.0, 8.0, 7.0]
        r2 = _screen_stock(db_session, sort="ret_5y", order="desc",
                           universe_codes=new_universe, page=2, limit=4)
        assert [it["ret_5y"] for it in r2["items"]] == [6.0, None, None, None]
