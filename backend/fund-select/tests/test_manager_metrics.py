"""manager_metrics 单测：纯函数，不联网。锚点断言来自前期实测。"""
from src.services.manager_metrics import (
    annualize,
    compute_risk,
    pick_representative,
    slice_series,
    weighted_annual,
)


def _t(code, ftype, days, ret, ann=None, current=True):
    return {"fund_code": code, "fund_type": ftype, "tenure_days": days,
            "tenure_return_pct": ret, "annual_return": ann, "is_current": current}


class TestAnnualize:
    def test_zhangkun_longest_tenure_anchor(self):
        """锚点：张坤 110011 任期 14年又46天（5186 天）累计 311.31% → ≈10.5%。"""
        ann = annualize(311.31, 14 * 365 + 46)
        assert ann == pytest_approx(10.53, 0.3)

    def test_zero_days_none(self):
        assert annualize(100.0, 0) is None
        assert annualize(100.0, None) is None
        assert annualize(None, 100) is None

    def test_wipeout_none(self):
        assert annualize(-100.0, 1000) is None
        assert annualize(-120.0, 1000) is None

    def test_short_tenure(self):
        # 82 天赚 0.28% → 年化约 1.25%
        ann = annualize(0.28, 82)
        assert ann == pytest_approx(((1.0028) ** (365 / 82) - 1) * 100, 1e-6)


def pytest_approx(expected, tol):
    """容差断言辅助（避免引入 pytest.approx 的相对/绝对歧义）。"""
    class _A:
        def __eq__(self, other):
            return other is not None and abs(other - expected) <= tol
    return _A()


class TestWeightedAnnual:
    def test_zhangkun_weighted_vs_longest(self):
        """锚点：张坤全段加权年化 ≈6.78%，必须低于最长任期单只 ≈10.53%。

        若实现退化为「只看最长任期」，等于让经理自选代表作。
        （早期调研手写 5.15% 用的是粗口径漏掉了灵活配置段；精确定义
        = 排除债基/货币/FOF 后全段加权，见 test_qdii_equity_included。）
        """
        tenures = [
            _t("110011", "QDII-混合", 14 * 365 + 46, 311.31, annualize(311.31, 14 * 365 + 46)),
            _t("118001", "QDII-普通", 12 * 365 + 219, 77.76, annualize(77.76, 12 * 365 + 219)),
            _t("005827", "混合型-偏股", 8 * 365 + 68, 39.93, annualize(39.93, 8 * 365 + 68)),
            _t("009342", "混合型-偏股", 6 * 365 + 106, -26.38, annualize(-26.38, 6 * 365 + 106)),
            _t("001373", "混合型-灵活", 5 * 365 + 98, 156.18, annualize(156.18, 5 * 365 + 98)),
        ]
        longest = max(t["annual_return"] for t in tenures)
        weighted = weighted_annual(tenures)
        assert weighted is not None
        assert weighted < longest
        assert weighted == pytest_approx(6.78, 0.1)

    def test_excludes_bond_segments(self):
        """债基段必须剔除：债基 20% 年化不该抬高股票经理排名。"""
        eq = [_t("a", "混合型-偏股", 3650, 100.0, annualize(100.0, 3650))]
        with_bond = eq + [_t("b", "债券型-长债", 3650, 400.0, 20.0)]
        assert weighted_annual(with_bond) == weighted_annual(eq)

    def test_qdii_equity_included(self):
        """口径回归：QDII-混合（偏股 QDII）必须计入。

        张坤任期最长的易方达优质精选(110011)是 QDII-混合；若按精确白名单
        漏掉它，加权年化会从 ≈5.2% 掉到 ≈0.3%（实测踩坑）。
        """
        tenures = [
            _t("110011", "QDII-混合", 14 * 365 + 46, 311.31, annualize(311.31, 14 * 365 + 46)),
            _t("005827", "混合型-偏股", 8 * 365 + 68, 39.93, annualize(39.93, 8 * 365 + 68)),
            _t("009342", "混合型-偏股", 6 * 365 + 106, -26.38, annualize(-26.38, 6 * 365 + 106)),
        ]
        weighted = weighted_annual(tenures)
        # 该三段子集精确定义下的加权值
        assert weighted == pytest_approx(5.36, 0.2)

    def test_empty_or_no_valid(self):
        assert weighted_annual([]) is None
        assert weighted_annual([_t("a", "混合型-偏股", 100, 50.0, None)]) is None

    def test_all_bond_none(self):
        assert weighted_annual([_t("b", "债券型-长债", 100, 5.0, 5.0)]) is None

    def test_money_and_fof_excluded(self):
        assert weighted_annual([_t("m", "货币型", 100, 1.0, 1.0)]) is None
        assert weighted_annual([_t("f", "FOF-稳健", 100, 2.0, 2.0)]) is None


class TestPickRepresentative:
    def test_prefers_active_equity_longest_current(self):
        tenures = [
            _t("bd", "债券型-长债", 9999, 100.0),
            _t("s", "混合型-偏股", 1000, 10.0),
            _t("l", "股票型", 5000, 50.0),
            _t("q", "QDII-混合", 8000, 90.0, current=False),
        ]
        assert pick_representative(tenures)["fund_code"] == "l"

    def test_falls_back_to_all_when_no_equity(self):
        tenures = [_t("b", "债券型-长债", 3000, 5.0)]
        assert pick_representative(tenures)["fund_code"] == "b"

    def test_empty_none(self):
        assert pick_representative([]) is None


class TestComputeRisk:
    def _flat_series(self, n=400, daily=0.0002):
        nav = 1.0
        out = []
        from datetime import date, timedelta
        d0 = date(2020, 1, 1)
        for i in range(n):
            out.append(((d0 + timedelta(days=i)).isoformat(), round(nav, 6)))
            nav *= 1 + daily
        return out

    def test_basic_metrics(self):
        series = self._flat_series()
        m = compute_risk(series)
        assert m is not None
        assert m["cagr_pct"] == pytest_approx((1.0002 ** 365 - 1) * 100, 0.3)
        assert m["max_drawdown_pct"] == pytest_approx(0.0, 0.01)
        assert m["sample_days"] == 399

    def test_drawdown_negative(self):
        series = self._flat_series(120, daily=0.001)
        # 末尾 30 点每天 -1%
        from datetime import date, timedelta
        d0 = date(2020, 1, 1)
        nav = series[-1][1]
        for i in range(30):
            nav *= 0.99
            series.append(((date(2020, 4, 30) + timedelta(days=i)).isoformat(), round(nav, 6)))
        m = compute_risk(series)
        assert m is not None
        assert m["max_drawdown_pct"] < -20

    def test_too_short_none(self):
        assert compute_risk(self._flat_series(10)) is None
        assert compute_risk([]) is None


class TestSliceSeries:
    """任职窗口切片：不切会把前任经理的业绩算到现任头上。"""

    SERIES = [("2010-01-01", 1.0), ("2012-09-27", 2.0), ("2012-09-28", 2.05),
              ("2020-01-01", 3.0), ("2026-11-10", 4.7)]

    def test_slice_by_start(self):
        out = slice_series(self.SERIES, start="2012-09-28")
        assert out[0] == ("2012-09-28", 2.05)
        assert len(out) == 3

    def test_slice_by_end(self):
        out = slice_series(self.SERIES, end="2020-01-01")
        assert out[-1] == ("2020-01-01", 3.0)

    def test_slice_window(self):
        out = slice_series(self.SERIES, start="2012-09-28", end="2020-01-01")
        assert out == [("2012-09-28", 2.05), ("2020-01-01", 3.0)]

    def test_no_slice(self):
        assert slice_series(self.SERIES) == self.SERIES
