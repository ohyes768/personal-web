"""夏普走势（现算滚动夏普）服务层 + API 测试

关键回归：**纯净值口径不受 fund_benchmark 截断**。构造有基准行但基准
起始日晚于净值起始日的基金，断言历史窗口 sample_days 仍为 3 年（≈729）
而非被 inner join 截到 1 年（219）——见 research/data-basis.md 实测：
000628 在 2024-09-30 窗口 join 版 2.42/n=219，纯净值版 0.68/n=729。

测试全部用合成净值序列（不依赖 akshare 网络），nav_fetch 用 monkeypatch。
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, Fund, FundBenchmark, RiskFreeRate
from src.services import sharpe_trend_service as svc
from src.services.sharpe_trend_service import (
    FundNotFoundError,
    NavFetchError,
    TrendPoint,
    build_trend,
    clear_nav_cache,
    compute_trend_stats,
    filter_range,
    nav_to_returns,
    rolling_sharpe_series,
    trim_leading_gaps,
)


# ──────────────────────────────────────────────────────────────────
# 合成净值工具
# ──────────────────────────────────────────────────────────────────

def make_nav(n_days: int, end: date = date(2026, 11, 12), seed: int = 42) -> pd.DataFrame:
    """生成 n_days 个交易日的单位净值 DataFrame（含「净值日期」「日增长率」）。

    收益率用固定种子的正态噪声（百分数），保证可重复且 std>0。
    """
    rng = np.random.default_rng(seed)
    # 用工作日近似交易日（跳过周末），从 end 往回取 n_days 个
    dates = []
    d = end
    while len(dates) < n_days:
        if d.weekday() < 5:
            dates.append(d)
        d -= timedelta(days=1)
    dates = sorted(pd.to_datetime(dates))
    growth = rng.normal(loc=0.04, scale=0.8, size=n_days)  # 百分数
    return pd.DataFrame({"净值日期": dates, "日增长率": growth})


@pytest.fixture
def trend_db():
    """in-memory SQLite + StaticPool（TestClient 线程共享同一连接）"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    # 默认预置一只基金：build_trend 现在要求 code 在 Fund 表内（不在 → 404），
    # 各用例默认用 "000001"。需要别的 code 的用例自行插入。
    db.add(Fund(code="000001", name="测试基金"))
    db.commit()
    yield db
    db.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个用例清缓存，避免 monkeypatch 的净值跨用例串味"""
    clear_nav_cache()
    yield
    clear_nav_cache()


# ──────────────────────────────────────────────────────────────────
# 1. 纯函数：滚动算法
# ──────────────────────────────────────────────────────────────────

class TestRollingSharpe:

    def test_empty_returns_no_points(self):
        assert rolling_sharpe_series(pd.Series(dtype=float), None) == []
        assert rolling_sharpe_series(None, None) == []

    def test_weekly_points_and_sample_days(self):
        nav = make_nav(900)
        r = nav_to_returns(nav)
        pts = rolling_sharpe_series(r, None)
        assert len(pts) > 100
        assert all(isinstance(p.date, date) for p in pts)
        # 前导点样本不足 → None；之后全为有效点，sample_days ≈ 3 年
        assert pts[0].sharpe is None and pts[0].sample_days < 250
        valid = [p for p in pts if p.sharpe is not None]
        assert valid and valid[-1].sample_days >= 700
        assert valid[-1].date == r.index.max().date()

    def test_std_zero_returns_none(self):
        """全零收益 → std=0 → sharpe 无定义（不出点）"""
        idx = pd.date_range("2022-01-03", periods=400, freq="B")
        r = pd.Series(np.zeros(400), index=idx)
        pts = rolling_sharpe_series(r, None)
        valid = [p for p in pts if p.sample_days >= 250]
        assert valid and all(p.sharpe is None for p in valid)

    def test_rf_lowers_sharpe(self):
        """rf>0 应系统性下调夏普（均值减去正数）"""
        nav = make_nav(900)
        r = nav_to_returns(nav)
        rf = pd.Series([0.02] * len(r), index=r.index)  # 年化 2%
        a = [p.sharpe for p in rolling_sharpe_series(r, None) if p.sharpe is not None]
        b = [p.sharpe for p in rolling_sharpe_series(r, rf) if p.sharpe is not None]
        assert a and len(a) == len(b)
        assert all(x > y for x, y in zip(a, b))

    def test_pure_nav_ignores_benchmark(self):
        """核心回归：rolling_sharpe_series 签名里根本没有 r_b，无法被截断。

        传一个「只在近 1 年有数据」的 rf 序列进去，逐点比较 sample_days
        与 sharpe：完全一致才证明短序列没有通过任何 join 缩窄历史窗口。
        另用长序列（≈8 年）验证早期历史点的窗口确实是完整 3 年（≈729）。
        """
        r = nav_to_returns(make_nav(1400))
        short_rf = pd.Series([0.0] * 200,
                             index=pd.date_range("2026-01-01", periods=200, freq="B"))
        a = rolling_sharpe_series(r, None)
        b = rolling_sharpe_series(r, short_rf)
        assert [(p.date, p.sharpe, p.sample_days) for p in a] == [
            (p.date, p.sharpe, p.sample_days) for p in b
        ]

        long_r = nav_to_returns(make_nav(2000))
        long_pts = rolling_sharpe_series(long_r, None)
        hist = [p for p in long_pts
                if date(2024, 1, 1) <= p.date <= date(2024, 12, 31)]
        assert hist and all(p.sample_days >= 700 for p in hist), (
            f"历史窗口应 ≈729，实际 {[p.sample_days for p in hist[:3]]}"
        )


# ──────────────────────────────────────────────────────────────────
# 2. 纯函数：稳定性 KPI
# ──────────────────────────────────────────────────────────────────

def pts(values):
    return [TrendPoint(date=date(2026, 1, 1) + timedelta(weeks=i), sharpe=v,
                       sample_days=729) for i, v in enumerate(values)]


class TestTrendStats:

    def test_empty_stats_does_not_crash(self):
        st = compute_trend_stats([])
        assert st.current is None and st.above_ratio is None and st.trend_12w is None
        assert st.valid_count == 0

    def test_single_point(self):
        st = compute_trend_stats(pts([1.2]))
        assert st.current == st.max == st.min == st.mean == 1.2
        assert st.above_count == 1 and st.above_ratio == 1.0
        assert st.consecutive_above == 1 and st.longest_below == 0
        assert st.trend_12w is None  # 单点无斜率

    def test_all_above(self):
        st = compute_trend_stats(pts([1.0, 1.1, 1.2, 1.3]))
        assert st.consecutive_above == 4 and st.longest_below == 0
        assert st.above_ratio == 1.0

    def test_all_below(self):
        st = compute_trend_stats(pts([0.5, 0.6, 0.7]))
        assert st.consecutive_above == 0 and st.longest_below == 3
        assert st.above_ratio == 0.0

    def test_mixed_runs_and_gaps(self):
        # None 缺口打断连续计数（不算达标也不算低于）
        values = [1.0, 1.0, 0.5, 0.5, 0.5, None, 1.0]
        st = compute_trend_stats(pts(values))
        assert st.above_count == 3 and st.valid_count == 6
        assert st.consecutive_above == 1          # 最后一段只有 1 个
        assert st.longest_below == 3              # 中间 3 个连续低于
        assert st.above_ratio == pytest.approx(0.5)

    def test_threshold_inclusive(self):
        """≥ 阈值算达标（与夏普榜单 min_sharpe=0.8 含等号一致）"""
        st = compute_trend_stats(pts([0.8, 0.79]))
        assert st.above_count == 1 and st.longest_below == 1

    def test_trend_12w_boundary(self):
        assert compute_trend_stats(pts([1.0] * 11)).trend_12w is None
        st = compute_trend_stats(pts(list(np.linspace(0.5, 1.5, 12))))
        assert st.trend_12w is not None and st.trend_12w > 0
        # 只取最近 12 个有效点
        assert compute_trend_stats(pts([1.0] * 12)).trend_12w == pytest.approx(0.0)

    def test_current_is_last_valid(self):
        st = compute_trend_stats(pts([0.5, 1.5, None]))
        assert st.current == 1.5  # 最后一个有效点，不是最后一个点


class TestHelpers:

    def test_trim_leading_gaps_keeps_middle(self):
        p = pts([None, None, 1.0, None, 1.2])
        out = trim_leading_gaps(p)
        assert [x.sharpe for x in out] == [1.0, None, 1.2]

    def test_filter_range_only_trims_points(self):
        p = [TrendPoint(date=date(2024, 1, 1), sharpe=1.0, sample_days=729)] + \
            [TrendPoint(date=date(2026, 1, 1) + timedelta(weeks=i), sharpe=1.0,
                        sample_days=729) for i in range(10)]
        out = filter_range(p, "1y", date(2026, 11, 13))
        assert all(x.date >= date(2025, 11, 13) for x in out)
        assert out[0].sample_days == 729  # 窗口没变
        assert filter_range(p, "all", date(2026, 11, 13)) == p


# ──────────────────────────────────────────────────────────────────
# 3. 编排层：build_trend（rf / 缓存 / 空态 / 错误）
# ──────────────────────────────────────────────────────────────────

class TestBuildTrend:

    def test_rf_missing_marks_zero(self, trend_db, monkeypatch):
        """生产库 risk_free_rate 为空 → rf_basis='zero' 且曲线正常产出"""
        monkeypatch.setattr(svc, "_load_nav", lambda code: make_nav(900))
        res = build_trend(trend_db, "000001")
        assert res.rf_basis == "zero"
        assert res.points and res.stats.current is not None
        assert res.algorithm_version == "trend-v1"
        assert res.diagnostics.get("insufficient_history") is None

    def test_rf_present_marks_rate(self, trend_db, monkeypatch):
        for i in range(10):
            trend_db.add(RiskFreeRate(
                date=date(2026, 1, 1) + timedelta(days=i),
                rate=0.02, source="test",
            ))
        trend_db.commit()
        monkeypatch.setattr(svc, "_load_nav", lambda code: make_nav(900))
        res = build_trend(trend_db, "000001")
        assert res.rf_basis == "rate"
        assert res.points

    def test_benchmark_rows_do_not_truncate_window(self, trend_db, monkeypatch):
        """最关键回归：有 fund_benchmark 行（且起始晚）也不得截断历史窗口。

        旧口径 compute_risk_metrics 会 inner join r_b → 早期窗口只剩 1 年样本。
        走势页必须全程 3 年窗口。
        """
        nav = make_nav(2000)  # ≈7.6 年，2024 年时已有完整 3 年窗口
        monkeypatch.setattr(svc, "_load_nav", lambda code: nav)
        # 基准只有近 1 年（复刻生产库 2023-11-08 起的特征）
        start = date(2025, 11, 1)
        for i in range(250):
            trend_db.add(FundBenchmark(
                code="000001", date=start + timedelta(days=i),
                tri=1000.0 + i, source="test",
            ))
        trend_db.commit()

        with_bench = build_trend(trend_db, "000001")
        # 与「完全无基准行」的结果逐点比较：sample_days / sharpe 必须一致
        trend_db.query(FundBenchmark).delete()
        trend_db.commit()
        clear_nav_cache()
        no_bench = build_trend(trend_db, "000001")

        assert [(p.date, p.sharpe, p.sample_days) for p in with_bench.points] == [
            (p.date, p.sharpe, p.sample_days) for p in no_bench.points
        ], "fund_benchmark 行影响了走势计算（旧口径 inner join 会截断窗口）"

        hist = [p for p in with_bench.points
                if date(2024, 1, 1) <= p.date <= date(2024, 12, 31)]
        assert hist, "应有 2024 年的点"
        assert all(p.sample_days >= 700 for p in hist), (
            "历史窗口被截断：sample_days 应 ≈729，实际 "
            f"{[p.sample_days for p in hist[:3]]}"
        )

    def test_name_from_fund_table(self, trend_db, monkeypatch):
        trend_db.get(Fund, "000001").name = "测试股票基金"
        trend_db.commit()
        monkeypatch.setattr(svc, "_load_nav", lambda code: make_nav(900))
        assert build_trend(trend_db, "000001").name == "测试股票基金"

    def test_code_not_in_fund_table_raises_404(self, trend_db, monkeypatch):
        """不在 Fund 表 → 直接 FundNotFoundError（API 404），不打网络。

        避免 akshare 对未知代码抛的解析异常被误判成 502 源故障。
        """
        calls = []
        monkeypatch.setattr(svc, "_load_nav", lambda code: calls.append(code) or make_nav(900))
        with pytest.raises(FundNotFoundError):
            build_trend(trend_db, "999999")
        assert calls == []

    def test_insufficient_history(self, trend_db, monkeypatch):
        monkeypatch.setattr(svc, "_load_nav", lambda code: make_nav(100))
        res = build_trend(trend_db, "000001")
        assert res.points == []
        assert res.diagnostics["insufficient_history"] is True
        assert res.stats.current is None

    def test_empty_nav_raises_not_found(self, trend_db, monkeypatch):
        monkeypatch.setattr(svc, "_load_nav", lambda code: pd.DataFrame())
        with pytest.raises(FundNotFoundError):
            build_trend(trend_db, "000001")

    def test_nav_failure_raises_nav_error(self, trend_db, monkeypatch):
        def boom(code):
            raise RuntimeError("network down")
        monkeypatch.setattr(svc, "_load_nav", boom)
        with pytest.raises(NavFetchError):
            build_trend(trend_db, "000001")

    def test_nav_failure_not_cached(self, trend_db, monkeypatch):
        """失败不进缓存：第二次调用会重新请求（可重试）"""
        calls = []

        def flaky(code):
            calls.append(code)
            if len(calls) == 1:
                raise RuntimeError("transient")
            return make_nav(900)

        monkeypatch.setattr(svc, "_load_nav", flaky)
        with pytest.raises(NavFetchError):
            build_trend(trend_db, "000001")
        res = build_trend(trend_db, "000001")
        assert res.points and len(calls) == 2

    def test_nav_cached_on_same_code(self, trend_db, monkeypatch):
        calls = []

        def counting(code):
            calls.append(code)
            return make_nav(900)

        monkeypatch.setattr(svc, "_load_nav", counting)
        build_trend(trend_db, "000001", "all")
        build_trend(trend_db, "000001", "1y")
        assert calls == ["000001"]  # 区间切换不重复打网络

    def test_range_trims_but_window_unchanged(self, trend_db, monkeypatch):
        monkeypatch.setattr(svc, "_load_nav", lambda code: make_nav(1400))
        all_res = build_trend(trend_db, "000001", "all", today=date(2026, 11, 13))
        one = build_trend(trend_db, "000001", "1y", today=date(2026, 11, 13))
        assert len(one.points) < len(all_res.points)
        # 重叠区间的点数值与 sample_days 完全一致（窗口没变）
        all_map = {p.date: p for p in all_res.points}
        for p in one.points:
            assert p.sharpe == all_map[p.date].sharpe
            assert p.sample_days == all_map[p.date].sample_days


# ──────────────────────────────────────────────────────────────────
# 4. API 层：路由顺序 / 错误语义 / DTO 字段齐全
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(trend_db, monkeypatch):
    monkeypatch.setattr(svc, "_load_nav", lambda code: make_nav(900))
    from src.db.session import get_db
    from src.main import app

    def _override():
        yield trend_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSharpeTrendAPI:

    def test_route_not_swallowed_by_code_route(self, client):
        """路由顺序铁律：/sharpe-trend/000001 不得被 /{code} 吞掉"""
        r = client.get("/api/funds/sharpe-trend/000001")
        assert r.status_code == 200, r.text
        assert r.json()["code"] == "000001"

    def test_all_top_level_fields_present(self, client):
        """contracts §3a：response_model 静默砍字段防护"""
        d = client.get("/api/funds/sharpe-trend/000001").json()
        for key in ("code", "name", "range", "rf_basis", "algorithm_version",
                    "threshold", "points", "stats", "diagnostics"):
            assert key in d, f"缺字段 {key}"
        s = d["stats"]
        for key in ("threshold", "current", "max", "min", "mean", "above_count",
                    "valid_count", "above_ratio", "consecutive_above",
                    "longest_below", "trend_12w"):
            assert key in s, f"stats 缺字段 {key}"
        assert d["points"]
        for key in ("date", "sharpe", "sample_days"):
            assert key in d["points"][0]

    def test_range_param(self, client):
        a = client.get("/api/funds/sharpe-trend/000001?range=all").json()
        b = client.get("/api/funds/sharpe-trend/000001?range=1y").json()
        assert b["range"] == "1y" and len(b["points"]) < len(a["points"])

    def test_invalid_range_422(self, client):
        assert client.get("/api/funds/sharpe-trend/000001?range=5y").status_code == 422

    def test_not_found_404(self, client, monkeypatch):
        monkeypatch.setattr(svc, "_load_nav", lambda code: pd.DataFrame())
        r = client.get("/api/funds/sharpe-trend/999999")
        assert r.status_code == 404
        assert "999999" in r.json()["detail"]

    def test_nav_failure_502(self, client, monkeypatch):
        def boom(code):
            raise RuntimeError("network down")
        monkeypatch.setattr(svc, "_load_nav", boom)
        r = client.get("/api/funds/sharpe-trend/000001")
        assert r.status_code == 502
        assert "network down" in r.json()["detail"]

    def test_insufficient_history_is_200_empty_state(self, client, monkeypatch):
        monkeypatch.setattr(svc, "_load_nav", lambda code: make_nav(100))
        r = client.get("/api/funds/sharpe-trend/000001")
        assert r.status_code == 200
        assert r.json()["points"] == []
        assert r.json()["diagnostics"]["insufficient_history"] is True
