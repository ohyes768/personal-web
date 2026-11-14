"""
夏普榜单步骤 2 测试：本轮采集捕获（SharpeRunCapture）与入选谓词等价性

对应 implement.md 步骤 2（AC2、AC6、AC7）：
- MetricsResult.returns_end_date：7 位置参数构造兼容；取 joined 样本最大日期
  （受基准 TRI 尾日约束，R7 不拿刷新日冒充净值日）
- refresh_fund_risks capture：B 网络失败但库里有旧高夏普 → capture 标失败
  证据、不含 B（后续发布不能用旧 B 值）；覆盖写隔离；有效无指标进诊断
- market_risk_refresh / market_full_pipeline / refresh_stock_funds_sync 三层
  capture 接线：冻结 universe / 预筛 / base_rows；阶段与基准错误汇入 errors；
  capture=None 旧路径行为不变
- entry_predicate 与 _screen SQL where 等价（负回撤绝对值、阈值等号、NULL、
  QDII 排除、精确 subtype——不是粗类别）

全程 mock，不联网。
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from src.db.models import Fund, FundBenchmark, FundPerformance, FundRiskMetrics, MarketFundRank
from src.services.filter_service import FilterService, entry_predicate
from src.services.market_full_pipeline import MAX_NAV_STALE_DAYS, refresh_market_full_sync
from src.services.market_risk_refresh import refresh as refresh_market_risk
from src.services.risk_service import MIN_SAMPLE_DAYS, MetricsResult, compute_risk_metrics, refresh_fund_risks
from src.services.sharpe_capture import SharpeRunCapture, freeze_base_row, freeze_base_rows


# ─────────────────────────────────────────────────────────────
# 合成 nav 数据
# ─────────────────────────────────────────────────────────────

def _nav_df(seed: int = 1, n: int = 800, end=None) -> pd.DataFrame:
    """≥250 交易日的有效 nav（日增长率 % 列）；不同 seed → 不同 sharpe。"""
    rng = np.random.default_rng(seed)
    g = rng.normal(0.0003, 0.001, n)
    dates = pd.bdate_range(end=end or pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"净值日期": dates, "日增长率": g * 100.0})


def _seed_fund(db, code: str, **kw):
    defaults = dict(code=code, name=f"基金{code}", market_subtype="股票型",
                    age_years=6.0, size_yi=10.0, mgr_experience_years=8.0,
                    is_active=True)
    defaults.update(kw)
    db.add(Fund(**defaults))


# ─────────────────────────────────────────────────────────────
# MetricsResult.returns_end_date
# ─────────────────────────────────────────────────────────────

class TestMetricsResultReturnsEndDate:
    def test_positional_construction_compat(self):
        """旧 7 位置参数构造仍有效；新字段默认 None（兼容性证明）"""
        m = MetricsResult(None, None, None, None, None, None, 0)
        assert m.returns_end_date is None
        d = date(2026, 11, 6)
        m2 = MetricsResult(0.9, None, None, None, None, None, 300, d)
        assert m2.sample_days == 300
        assert m2.returns_end_date == d

    def test_returns_end_date_is_joined_sample_max(self):
        """returns_end_date = 计算夏普的 joined 样本最大日期（受 TRI 尾日约束），
        不是今天/刷新日（R7：实际收益样本截止日）"""
        n = 300
        idx = pd.bdate_range("2026-01-01", periods=n)
        rng = np.random.default_rng(3)
        r_p = pd.Series(rng.normal(0.001, 0.01, n), index=idx)
        # 基准尾日早 10 天 → inner join 后样本尾日 = idx[n-11]
        r_b = pd.Series(rng.normal(0.0, 0.01, n - 10), index=idx[: n - 10])
        r_f = pd.Series(0.0, index=idx)

        m = compute_risk_metrics(r_p, r_b, r_f)

        assert m.returns_end_date == idx[n - 11].date()
        assert m.sample_days == n - 10

    def test_full_overlap_join_max_is_last_day(self):
        """基准与净值全重叠 → joined 尾日 = 净值尾日"""
        n = 300
        idx = pd.bdate_range("2026-01-01", periods=n)
        rng = np.random.default_rng(4)
        r_p = pd.Series(rng.normal(0.001, 0.01, n), index=idx)
        r_b = pd.Series(rng.normal(0.0, 0.01, n), index=idx)
        r_f = pd.Series(0.0, index=idx)
        m = compute_risk_metrics(r_p, r_b, r_f)
        assert m.returns_end_date == idx[-1].date()

    def test_insufficient_sample_no_end_date(self):
        """样本不足（指标全 None）→ 尾日 None（未知就标未知，不入选无观测）"""
        n = MIN_SAMPLE_DAYS - 1
        r = pd.Series([0.01] * n, index=pd.bdate_range("2026-01-01", periods=n))
        m = compute_risk_metrics(r, r.copy(), r.copy())
        assert m.sharpe is None
        assert m.returns_end_date is None

    def test_none_inputs_no_end_date(self):
        m = compute_risk_metrics(None, None, None)
        assert m.returns_end_date is None


# ─────────────────────────────────────────────────────────────
# refresh_fund_risks capture
# ─────────────────────────────────────────────────────────────

class TestRefreshFundRisksCapture:
    def test_nav_failure_captured_not_old_value(self, db_session, monkeypatch):
        """关键测试 A：本轮 A 成功、B 网络失败但库里 B 有旧高夏普
        → capture 必须标失败证据、B 不进 risk_rows（后续发布不能用旧 B 值）。
        _safe_fetch_nav 吞异常 → 返回 errors 为空，capture 是唯一证据渠道。
        """
        _seed_fund(db_session, "000001")
        _seed_fund(db_session, "000002")
        # 库里 B 有旧高夏普（共享最新表只有最新值）
        db_session.add(FundRiskMetrics(code="000002", sharpe=1.5,
                                       as_of_date=date(2026, 10, 30)))
        db_session.commit()

        def fake_nav(code):
            if code == "000002":
                raise RuntimeError("东财网络超时")
            return _nav_df(seed=1)

        monkeypatch.setattr("src.services.risk_service.fetch_nav", fake_nav)

        cap = SharpeRunCapture(run_id="run-a")
        errors = refresh_fund_risks(db_session, ["000001", "000002"], capture=cap)

        # research 陷阱：returned failed 漏报（nav 异常被吞）→ errors 为空
        assert errors == []
        # capture 才是失败证据渠道：B 网络失败必须留下
        assert any("000002" in e for e in cap.errors), f"capture.errors={cap.errors}"
        # B 本轮无有效风险值 → 不能被旧 1.5 冒充
        assert "000002" not in cap.risk_rows
        # A 正常冻结
        assert "000001" in cap.risk_rows
        assert cap.risk_rows["000001"]["sharpe"] is not None

    def test_capture_snapshot_not_polluted_by_later_overwrite(self, db_session, monkeypatch):
        """共享最新表被另一次普通刷新覆盖：capture 字段和风险仍来自本轮"""
        _seed_fund(db_session, "000001")
        db_session.commit()

        monkeypatch.setattr("src.services.risk_service.fetch_nav",
                            lambda code: _nav_df(seed=1))
        cap = SharpeRunCapture(run_id="run-1")
        refresh_fund_risks(db_session, ["000001"], capture=cap)
        first_sharpe = cap.risk_rows["000001"]["sharpe"]
        first_end = cap.risk_rows["000001"]["returns_end_date"]

        # 另一次普通刷新（capture=None）覆盖库行：数据完全不同
        monkeypatch.setattr("src.services.risk_service.fetch_nav",
                            lambda code: _nav_df(seed=99))
        refresh_fund_risks(db_session, ["000001"])
        row_now = db_session.get(FundRiskMetrics, "000001")

        assert cap.risk_rows["000001"]["sharpe"] == first_sharpe
        assert cap.risk_rows["000001"]["returns_end_date"] == first_end
        # 覆盖确实发生了（库行 ≠ capture 快照），证明测试有效
        assert row_now.sharpe != first_sharpe

    def test_valid_data_missing_metrics_goes_to_diagnostics(self, db_session, monkeypatch):
        """数据有效但指标无定义（样本不足）→ diagnostics，不算采集失败（R6）"""
        _seed_fund(db_session, "000001")
        db_session.commit()
        monkeypatch.setattr("src.services.risk_service.fetch_nav",
                            lambda code: _nav_df(seed=2, n=100))  # < 250 天

        cap = SharpeRunCapture(run_id="run-d")
        errors = refresh_fund_risks(db_session, ["000001"], capture=cap)

        assert errors == []
        assert cap.errors == []
        assert cap.diagnostics.get("metrics_undefined") == ["000001"]
        assert cap.risk_rows["000001"]["sharpe"] is None

    def test_risk_rows_carry_returns_end_date_and_source(self, db_session, monkeypatch):
        """risk_rows 冻结本轮风险值 + 实际样本尾日 + 基准来源（QDII skipped 行）"""
        _seed_fund(db_session, "000001", market_subtype="QDII-普通股票")
        db_session.add(FundBenchmark(code="000001", date=date(2026, 9, 1),
                                     tri=None, source="skipped:qdii"))
        db_session.commit()
        monkeypatch.setattr("src.services.risk_service.fetch_nav",
                            lambda code: _nav_df(seed=3))

        cap = SharpeRunCapture(run_id="run-q")
        refresh_fund_risks(db_session, ["000001"], capture=cap)

        entry = cap.risk_rows["000001"]
        assert entry["sharpe"] is not None
        assert entry["returns_end_date"] is not None
        assert isinstance(entry["returns_end_date"], date)
        assert entry["benchmark_source"] == "skipped:qdii"

    def test_capture_none_path_unchanged(self, db_session, monkeypatch):
        """capture=None：返回 errors 列表照旧、不炸（旧路径回归）"""
        _seed_fund(db_session, "000001")
        db_session.commit()
        monkeypatch.setattr("src.services.risk_service.fetch_nav",
                            lambda code: _nav_df(seed=1))
        errors = refresh_fund_risks(db_session, ["000001"])
        assert errors == []

    def test_exception_still_reported_and_capture_freezes_others(self, db_session, monkeypatch):
        """真异常（非 nav 网络失败）路径：返回 errors 照旧；其余基金照常冻结"""
        _seed_fund(db_session, "000001")
        _seed_fund(db_session, "000002")
        db_session.commit()
        # benchmark 查询本身炸（模拟意外异常）
        real_nav = _nav_df(seed=1)

        def fake_nav(code):
            if code == "000002":
                raise RuntimeError("boom")
            return real_nav

        monkeypatch.setattr("src.services.risk_service.fetch_nav", fake_nav)
        cap = SharpeRunCapture(run_id="run-e")
        errors = refresh_fund_risks(db_session, ["000001", "000002"], capture=cap)
        # nav 异常被 capture 分支捕获 → 不进返回 errors，进 capture.errors
        assert errors == []
        assert any("000002" in e for e in cap.errors)
        assert "000001" in cap.risk_rows


# ─────────────────────────────────────────────────────────────
# market_risk_refresh capture 接线
# ─────────────────────────────────────────────────────────────

class TestMarketRiskRefreshCapture:
    def test_capture_passed_through_to_fund_risks(self, db_session):
        """capture 透传给 refresh_fund_risks"""
        seen = {}

        def fake_risk(db, codes, capture=None):
            seen["capture"] = capture
            return []

        with patch(
            "src.services.market_risk_refresh.benchmark_refresh.refresh",
            side_effect=lambda db, codes: [],
        ), patch(
            "src.services.market_risk_refresh.refresh_fund_risks",
            side_effect=fake_risk,
        ):
            cap = SharpeRunCapture(run_id="run-p")
            refresh_market_risk(db_session, ["673010"], capture=cap)

        assert seen["capture"] is cap

    def test_benchmark_errors_merged_into_capture(self, db_session):
        """基准错误汇入 capture.errors（有输入采集错误则本轮不得发布完整榜）"""
        bench_errors = ["benchmark:999999: fetch failed"]

        with patch(
            "src.services.market_risk_refresh.benchmark_refresh.refresh",
            side_effect=lambda db, codes: list(bench_errors),
        ), patch(
            "src.services.market_risk_refresh.refresh_fund_risks",
            side_effect=lambda db, codes, capture=None: [],
        ):
            cap = SharpeRunCapture(run_id="run-b")
            result = refresh_market_risk(db_session, ["999999"], capture=cap)

        assert result["errors"] == bench_errors        # 返回值行为不变
        assert cap.errors == bench_errors              # capture 同步持有

    def test_risk_errors_merged_into_capture(self, db_session):
        """风险错误汇入 capture.errors"""
        risk_errors = ["risk:888888: tri missing"]

        with patch(
            "src.services.market_risk_refresh.benchmark_refresh.refresh",
            side_effect=lambda db, codes: [],
        ), patch(
            "src.services.market_risk_refresh.refresh_fund_risks",
            side_effect=lambda db, codes, capture=None: list(risk_errors),
        ):
            cap = SharpeRunCapture(run_id="run-r")
            refresh_market_risk(db_session, ["888888"], capture=cap)

        assert cap.errors == risk_errors

    def test_capture_none_call_form_unchanged(self, db_session):
        """capture=None：调用形态与旧路径一致（mock 签名不带 capture 也能跑）"""
        with patch(
            "src.services.market_risk_refresh.benchmark_refresh.refresh",
            side_effect=lambda db, codes: [],
        ), patch(
            "src.services.market_risk_refresh.refresh_fund_risks",
            side_effect=lambda db, codes: [],  # 旧签名 mock
        ):
            result = refresh_market_risk(db_session, ["673010"])

        assert result["failed"] == 0


# ─────────────────────────────────────────────────────────────
# market_full_pipeline capture 接线
# ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def stable_pipeline_date(monkeypatch):
    """L1 后预筛含 nav_date 新鲜度检查；fixture nav 定在 2026-09-07，
    冻结 pipeline 的 today 使断言与真实日期无关（对齐 test_market_full_pipeline）。"""
    class FixtureDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 7)

    monkeypatch.setattr("src.services.market_full_pipeline.date", FixtureDate)


class TestMarketFullPipelineCapture:
    """复用 test_market_full_pipeline 的全量 fetcher mock（不联网）。"""

    def _seed_stock_universe(self, db_session):
        db_session.add(_mk_pipeline_fund("300001", "股票型", size_yi=10,
                                         age_years=6, mgr_experience_years=8.0))
        db_session.add(MarketFundRank(code="300001", nav_date=date(2026, 9, 7),
                                      ret_3y=25.0, ft_code="gp"))
        db_session.commit()

    def test_stock_profile_freezes_universe_prefilters_base_rows(self, db_session, monkeypatch):
        from tests.test_market_full_pipeline import TestRefreshMarketFullSync
        TestRefreshMarketFullSync()._mock_all_fetchers(monkeypatch)
        self._seed_stock_universe(db_session)

        cap = SharpeRunCapture(run_id="run-m")
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(
                universe_filter=["股票型"],
                min_ret_3y=20, min_size_yi=5, min_mgr_exp=5,
                preset_task_id="test-cap-mkt",
                capture=cap,
            )

        assert result["universe_size"] == 1
        # universe 冻结（最终 codes）
        assert cap.universe_codes == ["300001"]
        # 采集预筛冻结（含后端 nav 新鲜度常量）
        assert cap.collection_prefilters == {
            "min_ret_3y": 20, "min_size_yi": 5, "min_mgr_exp": 5,
            "max_nav_stale_days": MAX_NAV_STALE_DAYS,
        }
        # 基础字段冻结（L2 commit 后的 Fund 行快照）
        assert cap.base_rows["300001"]["market_subtype"] == "股票型"
        assert cap.base_rows["300001"]["size_yi"] == 10.0
        assert cap.base_rows["300001"]["mgr_experience_years"] == 8.0

    def test_bond_profile_ignores_capture(self, db_session, monkeypatch):
        """债基不接夏普：bond profile 下 capture 不被填充"""
        from tests.test_market_full_pipeline import TestPipelineProfile
        TestPipelineProfile()._mock_all_fetchers(monkeypatch)
        TestPipelineProfile()._seed_funds(db_session)

        cap = SharpeRunCapture(run_id="run-bond")
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            refresh_market_full_sync(
                universe_filter=["债券型-中短债", "债券型-长期纯债"],
                pipeline_profile="bond",
                preset_task_id="test-cap-bond",
                capture=cap,
            )

        assert cap.universe_codes == []
        assert cap.base_rows == {}
        assert cap.collection_prefilters == {}
        assert cap.errors == []

    def test_l4_receives_capture(self, db_session, monkeypatch):
        """L4 风险刷新收到 capture（风险值由 risk 层冻结）"""
        from tests.test_market_full_pipeline import TestRefreshMarketFullSync
        TestRefreshMarketFullSync()._mock_all_fetchers(monkeypatch)
        self._seed_stock_universe(db_session)

        seen = {}

        def fake_risk(db, codes, task_id=None, capture=None):
            seen["capture"] = capture
            return {"task_id": task_id, "total": len(codes),
                    "completed": len(codes), "failed": 0, "errors": []}

        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_risk_db", fake_risk)

        cap = SharpeRunCapture(run_id="run-l4")
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            refresh_market_full_sync(
                universe_filter=["股票型"], preset_task_id="test-cap-l4", capture=cap)

        assert seen["capture"] is cap

    def test_stage_error_merged_into_capture(self, db_session, monkeypatch):
        """任一阶段失败 → capture.errors（本轮不得发布完整榜，design 第 4 条）"""
        from tests.test_market_full_pipeline import TestRefreshMarketFullSync
        TestRefreshMarketFullSync()._mock_all_fetchers(monkeypatch)
        self._seed_stock_universe(db_session)

        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_size",
            lambda codes, **kw: (_ for _ in ()).throw(RuntimeError("L2 boom")),
        )

        cap = SharpeRunCapture(run_id="run-err")
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            refresh_market_full_sync(
                universe_filter=["股票型"], preset_task_id="test-cap-err", capture=cap)

        assert any("stage:L2_size" in e for e in cap.errors), f"errors={cap.errors}"

    def test_capture_none_pipeline_unchanged(self, db_session, monkeypatch):
        """capture=None：pipeline 照旧跑完 6 阶段（旧路径回归）"""
        from tests.test_market_full_pipeline import TestRefreshMarketFullSync
        TestRefreshMarketFullSync()._mock_all_fetchers(monkeypatch)
        self._seed_stock_universe(db_session)

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(
                universe_filter=["股票型"], preset_task_id="test-cap-none")

        assert set(result["stage_results"].keys()) == {
            "L0_universe", "L1_rank", "L2_size", "L3_nav", "L4_risk", "L5_achievement"}


def _mk_pipeline_fund(code: str, market_subtype: str, **kw):
    """pipeline 测试基金工厂（对齐 test_market_full_pipeline._mk_fund）"""
    defaults = dict(
        code=code, name=f"基金{code}", market_subtype=market_subtype,
        market_type="stock", fund_type="股票型",
        age_years=5.0, size_yi=10.0, is_active=True,
    )
    defaults.update(kw)
    return Fund(**defaults)


# ─────────────────────────────────────────────────────────────
# refresh_stock_funds_sync（雪球三分法链路）capture 接线
# ─────────────────────────────────────────────────────────────

def _fake_snapshot_ok(code, mgr_wt, mgr_co, fetch_holdings=False, fetch_ranking=True):
    return {
        "code": code, "name": f"股基{code}", "fund_type": "股票型",
        "age_years": 6.0, "size_yi": 20.0,
        "mgr_name": "张三", "mgr_company": "某司",
        "mgr_days": 2900, "mgr_experience_years": 8.0,
        "performance": {"ret_3y": 10.0, "dd_3y": -5.0, "as_of_date": date(2026, 9, 1)},
        "fees": {"fee_mgmt": 0.3, "fee_custody": 0.1},
        "is_active": True,
    }


class TestStockRefreshCapture:
    def _run_stock_refresh(self, db_session, monkeypatch, capture, snapshot=None):
        monkeypatch.setattr("src.scheduler.tasks.load_fund_codes",
                            lambda path=None: ["300001", "300002"])
        monkeypatch.setattr("src.scheduler.tasks.fetch_manager_table",
                            lambda use_cache=True: ({}, {}))
        monkeypatch.setattr("src.scheduler.tasks.snapshot_fund",
                            snapshot or _fake_snapshot_ok)
        monkeypatch.setattr("src.services.benchmark_refresh.refresh",
                            lambda db, codes: [])
        monkeypatch.setattr("src.services.risk_service.refresh_fund_risks",
                            lambda db, codes, capture=None: [])
        with patch("src.scheduler.tasks.SessionLocal", return_value=db_session):
            from src.scheduler.tasks import refresh_stock_funds_sync
            return refresh_stock_funds_sync(preset_task_id="test-stock-cap", capture=capture)

    def test_base_rows_and_universe_frozen_after_commit(self, db_session, monkeypatch):
        """每只 commit 后冻结 Fund 行筛选字段；名单确定后冻结 universe"""
        cap = SharpeRunCapture(run_id="run-s1")
        result = self._run_stock_refresh(db_session, monkeypatch, cap)

        assert result["failed"] == 0
        assert cap.universe_codes == ["300001", "300002"]
        assert set(cap.base_rows.keys()) == {"300001", "300002"}
        # freeze_base_row 从 DB 读 persist_snapshot 刚写入的 Fund 行
        assert cap.base_rows["300001"]["name"] == "股基300001"
        assert cap.base_rows["300001"]["age_years"] == 6.0
        assert cap.base_rows["300001"]["size_yi"] == 20.0

    def test_snapshot_failure_enters_capture_errors(self, db_session, monkeypatch):
        """snapshot 3 次重试耗尽 → capture.errors（本轮不得发布完整榜）"""
        def flaky(code, mgr_wt, mgr_co, fetch_holdings=False, fetch_ranking=True):
            if code == "300002":
                raise RuntimeError("雪球接口挂了")
            return _fake_snapshot_ok(code, mgr_wt, mgr_co)

        cap = SharpeRunCapture(run_id="run-s2")
        result = self._run_stock_refresh(db_session, monkeypatch, cap, snapshot=flaky)

        assert result["failed"] == 1
        assert any("300002" in e for e in cap.errors)
        # 失败那只不进 base_rows（本轮无 commit）
        assert set(cap.base_rows.keys()) == {"300001"}

    def test_benchmark_risk_errors_merged_into_capture(self, db_session, monkeypatch):
        """基准/风险返回错误汇入 capture.errors（research：returned failed 会漏报，
        capture.errors 是发布侧判定证据）"""
        monkeypatch.setattr("src.scheduler.tasks.load_fund_codes",
                            lambda path=None: ["300001"])
        monkeypatch.setattr("src.scheduler.tasks.fetch_manager_table",
                            lambda use_cache=True: ({}, {}))
        monkeypatch.setattr("src.scheduler.tasks.snapshot_fund", _fake_snapshot_ok)
        monkeypatch.setattr("src.services.benchmark_refresh.refresh",
                            lambda db, codes: ["benchmark:300001: tri fail"])
        monkeypatch.setattr("src.services.risk_service.refresh_fund_risks",
                            lambda db, codes, capture=None: ["risk:300001: nav fail"])

        cap = SharpeRunCapture(run_id="run-s3")
        with patch("src.scheduler.tasks.SessionLocal", return_value=db_session):
            from src.scheduler.tasks import refresh_stock_funds_sync
            refresh_stock_funds_sync(preset_task_id="test-stock-cap3", capture=cap)

        assert any("benchmark:300001" in e for e in cap.errors)
        assert any("risk:300001" in e for e in cap.errors)

    def test_risk_capture_kwarg_forwarded(self, db_session, monkeypatch):
        """capture 透传给 refresh_fund_risks"""
        seen = {}
        monkeypatch.setattr("src.scheduler.tasks.load_fund_codes",
                            lambda path=None: ["300001"])
        monkeypatch.setattr("src.scheduler.tasks.fetch_manager_table",
                            lambda use_cache=True: ({}, {}))
        monkeypatch.setattr("src.scheduler.tasks.snapshot_fund", _fake_snapshot_ok)
        monkeypatch.setattr("src.services.benchmark_refresh.refresh", lambda db, codes: [])

        def fake_risk(db, codes, capture=None):
            seen["capture"] = capture
            return []

        monkeypatch.setattr("src.services.risk_service.refresh_fund_risks", fake_risk)

        cap = SharpeRunCapture(run_id="run-s4")
        with patch("src.scheduler.tasks.SessionLocal", return_value=db_session):
            from src.scheduler.tasks import refresh_stock_funds_sync
            refresh_stock_funds_sync(preset_task_id="test-stock-cap4", capture=cap)

        assert seen["capture"] is cap

    def test_capture_none_stock_path_unchanged(self, db_session, monkeypatch):
        """capture=None：返回 dict 结构照旧（旧路径回归）"""
        result = self._run_stock_refresh(db_session, monkeypatch, None)
        assert set(result.keys()) == {"task_id", "total", "completed", "failed"}
        assert result["completed"] == 2


# ─────────────────────────────────────────────────────────────
# freeze_base_row / freeze_base_rows
# ─────────────────────────────────────────────────────────────

class TestFreezeBaseRow:
    def test_freeze_reads_current_row_values(self, db_session):
        _seed_fund(db_session, "000001", size_yi=42.0)
        db_session.commit()
        row = freeze_base_row(db_session, "000001")
        # 断言关键字段而非全等：v2 起 BASE_ROW_FIELDS 还含
        # mgr_experience_years_max（AC11），全等断言会随字段扩展反复失败。
        assert row["name"] == "基金000001"
        assert row["market_subtype"] == "股票型"
        assert row["age_years"] == 6.0
        assert row["size_yi"] == 42.0
        assert row["mgr_experience_years"] == 8.0

    def test_freeze_is_snapshot_not_live_reference(self, db_session):
        """冻结后修改 Fund 行，快照不变（纯拷贝）"""
        _seed_fund(db_session, "000001")
        db_session.commit()
        row = freeze_base_row(db_session, "000001")
        fund = db_session.get(Fund, "000001")
        fund.size_yi = 999.0
        db_session.commit()
        assert row["size_yi"] == 10.0

    def test_freeze_missing_code_returns_none(self, db_session):
        assert freeze_base_row(db_session, "999999") is None

    def test_freeze_rows_skips_missing(self, db_session):
        _seed_fund(db_session, "000001")
        db_session.commit()
        out = freeze_base_rows(db_session, ["000001", "888888"])
        assert set(out.keys()) == {"000001"}


# ─────────────────────────────────────────────────────────────
# capture 规则快照字段
# ─────────────────────────────────────────────────────────────

class TestCaptureRuleSnapshot:
    def test_filters_and_prefilters_stored_on_capture(self):
        """筛选条件与市场采集预筛一起随 capture 保存（发布侧入 evidence）"""
        cap = SharpeRunCapture(
            run_id="run-f",
            filters={"min_sharpe": 0.8, "min_age": 3},
            collection_prefilters={"min_ret_3y": 20},
        )
        assert cap.filters == {"min_sharpe": 0.8, "min_age": 3}
        assert cap.collection_prefilters == {"min_ret_3y": 20}

    def test_default_fields_empty_not_none(self):
        cap = SharpeRunCapture(run_id="run-f2")
        assert cap.base_rows == {}
        assert cap.risk_rows == {}
        assert cap.errors == []
        assert cap.diagnostics == {}
        assert cap.universe_codes == []

    def test_has_errors_reflects_input_failures(self):
        cap = SharpeRunCapture(run_id="run-f3")
        assert not cap.errors
        cap.add_error("risk:nav:000002: timeout")
        assert cap.errors == ["risk:nav:000002: timeout"]


# ─────────────────────────────────────────────────────────────
# entry_predicate 与 SQL 筛选等价性（同一 seed，两种求值）
# ─────────────────────────────────────────────────────────────

UNIVERSE = [f"6000{i:02d}" for i in range(1, 11)]


def _seed_equivalence_universe(db):
    """覆盖边界的 10 只：
    600001 sharpe 1.2 / dd -15
    600002 sharpe 0.8（等号）/ dd -10（等号）
    600003 sharpe 0.5 / dd -8
    600004 无风险行（sharpe None）
    600005 sharpe 0.9 / age None
    600006 market_subtype None（QDII 排除应保留）
    600007 market_subtype QDII-股票（排除）
    600008 market_subtype 互认基金（排除）
    600009 market_subtype ""（QDII 排除应保留）
    600010 mgr_experience None
    """
    def mk(code, **kw):
        defaults = dict(code=code, name=f"股基{code}", fund_type="股票型",
                        age_years=4.0, size_yi=10.0, mgr_name="张", mgr_company="某司",
                        mgr_days=2000, mgr_experience_years=5.5, is_active=True)
        defaults.update(kw)
        return Fund(**defaults)

    db.add_all([
        mk("600001"), mk("600002"), mk("600003"), mk("600004"),
        mk("600005", age_years=None),
        mk("600006", market_subtype=None),
        mk("600007", market_subtype="QDII-股票"),
        mk("600008", market_subtype="互认基金"),
        mk("600009", market_subtype=""),
        mk("600010", mgr_experience_years=None),
    ])
    db.add_all([
        FundPerformance(code="600001", as_of_date=date(2026, 9, 1), dd_3y=-15.0),
        FundPerformance(code="600002", as_of_date=date(2026, 9, 1), dd_3y=-10.0),
        FundPerformance(code="600003", as_of_date=date(2026, 9, 1), dd_3y=-8.0),
        FundPerformance(code="600004", as_of_date=date(2026, 9, 1), dd_3y=-5.0),
        FundPerformance(code="600005", as_of_date=date(2026, 9, 1), dd_3y=-7.0),
        FundPerformance(code="600006", as_of_date=date(2026, 9, 1), dd_3y=-6.0),
        FundPerformance(code="600007", as_of_date=date(2026, 9, 1), dd_3y=-6.0),
        FundPerformance(code="600008", as_of_date=date(2026, 9, 1), dd_3y=-6.0),
        FundPerformance(code="600009", as_of_date=date(2026, 9, 1), dd_3y=-6.0),
        FundPerformance(code="600010", as_of_date=date(2026, 9, 1), dd_3y=-6.0),
    ])
    db.add_all([
        FundRiskMetrics(code="600001", sharpe=1.2, as_of_date=date(2026, 9, 1)),
        FundRiskMetrics(code="600002", sharpe=0.8, as_of_date=date(2026, 9, 1)),
        FundRiskMetrics(code="600003", sharpe=0.5, as_of_date=date(2026, 9, 1)),
        FundRiskMetrics(code="600005", sharpe=0.9, as_of_date=date(2026, 9, 1)),
    ])
    db.commit()


def _collect_predicate_rows(db, codes=None) -> list[SimpleNamespace]:
    """从同一 DB 组装谓词输入行（与 capture 冻结 dict 同构）"""
    rows = db.execute(
        select(Fund, FundPerformance, FundRiskMetrics)
        .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
        .outerjoin(FundRiskMetrics, Fund.code == FundRiskMetrics.code)
        .where(Fund.code.in_(codes or UNIVERSE))
    ).all()
    return [
        SimpleNamespace(
            code=f.code, market_subtype=f.market_subtype,
            age_years=f.age_years, size_yi=f.size_yi,
            mgr_experience_years=f.mgr_experience_years,
            dd_3y=p.dd_3y if p else None,
            sharpe=r.sharpe if r else None,
        )
        for f, p, r in rows
    ]


class TestEntryPredicateEquivalence:
    """实时 SQL 筛选（_screen）与冻结数据谓词共用同一份阈值语义。

    不修改旧筛选测试断言；等价性由本类用旧查询结果作对照证明。
    """

    PARAM_SETS = [
        {},
        dict(min_age=3, min_size_yi=5, max_dd_3y=30, min_mgr_exp=5, min_sharpe=0.8),
        dict(max_dd_3y=10),
        dict(min_sharpe=0.8),
        dict(min_age=3),
        dict(min_mgr_exp=5.5),
        dict(exclude_qdii=True),
        dict(exclude_qdii=True, min_sharpe=0.8, max_dd_3y=10,
             min_age=3, min_size_yi=5, min_mgr_exp=5),
    ]

    def test_predicate_matches_sql_across_param_sets(self, db_session):
        _seed_equivalence_universe(db_session)
        rows = _collect_predicate_rows(db_session)
        for params in self.PARAM_SETS:
            sql_codes = {
                it["code"]
                for it in FilterService(db_session).screen_stock(
                    universe_codes=UNIVERSE, **params)["items"]
            }
            pred_codes = {r.code for r in rows if entry_predicate(**params)(r)}
            assert sql_codes == pred_codes, f"参数 {params} 下 SQL 与谓词不一致"

    def test_dd3y_boundary_equality_is_inclusive(self, db_session):
        """负回撤绝对值语义含等号：max_dd_3y=10 → dd=-10 留、-15 淘汰"""
        _seed_equivalence_universe(db_session)
        pred = entry_predicate(max_dd_3y=10)
        rows = {r.code: r for r in _collect_predicate_rows(db_session)}
        assert pred(rows["600002"]) is True   # dd=-10，等号命中
        assert pred(rows["600001"]) is False  # dd=-15
        assert pred(rows["600004"]) is True   # dd=-5

    def test_min_sharpe_boundary_equality_and_null(self, db_session):
        """min_sharpe=0.8 含等号；NULL（600004 无风险行）不命中"""
        _seed_equivalence_universe(db_session)
        pred = entry_predicate(min_sharpe=0.8)
        rows = {r.code: r for r in _collect_predicate_rows(db_session)}
        assert pred(rows["600002"]) is True   # 0.8 等号命中
        assert pred(rows["600001"]) is True   # 1.2
        assert pred(rows["600003"]) is False  # 0.5
        assert pred(rows["600004"]) is False  # sharpe None

    def test_null_dimensions_excluded_when_threshold_set(self, db_session):
        """任一所选维度为 None → 不命中（SQL NULL 比较为 falsy 的对齐）"""
        _seed_equivalence_universe(db_session)
        rows = {r.code: r for r in _collect_predicate_rows(db_session)}
        assert entry_predicate(min_age=3)(rows["600005"]) is False        # age None
        assert entry_predicate(min_mgr_exp=5)(rows["600010"]) is False    # mgr None
        # 不设该阈值时 None 不影响
        assert entry_predicate(min_age=3)(rows["600010"]) is True

    def test_exclude_qdii_uses_market_subtype_not_coarse(self, db_session):
        """QDII 排除按 market_subtype：QDII-股票 / 互认基金 丢；None / 空串保留"""
        _seed_equivalence_universe(db_session)
        pred = entry_predicate(exclude_qdii=True)
        rows = {r.code: r for r in _collect_predicate_rows(db_session)}
        assert pred(rows["600007"]) is False  # QDII-股票
        assert pred(rows["600008"]) is False  # 互认基金
        assert pred(rows["600006"]) is True   # None 保留（与 SQL NULL 保留一致）
        assert pred(rows["600009"]) is True   # 空串保留（与 SQL '' 保留一致）
        # 不排除时全部通过
        pred_no = entry_predicate()
        for r in _collect_predicate_rows(db_session):
            assert pred_no(r) is True

    def test_predicate_accepts_frozen_dict(self, db_session):
        """capture 冻结 dict（base_rows 形态）+ 风险值合并后可被谓词评估"""
        _seed_equivalence_universe(db_session)
        base = freeze_base_rows(db_session, UNIVERSE)
        risk = {"600001": {"sharpe": 1.2}, "600002": {"sharpe": 0.8}}
        dd = {r["code"]: r["dd_3y"] for r in (
            {"code": it.code, "dd_3y": it.dd_3y} for it in _collect_predicate_rows(db_session))}

        def frozen_row(code):
            return {**base[code], "sharpe": risk.get(code, {}).get("sharpe"),
                    "dd_3y": dd.get(code)}

        pred = entry_predicate(min_sharpe=0.8, max_dd_3y=30)
        passing = {c for c in UNIVERSE if pred(frozen_row(c))}
        assert passing == {"600001", "600002"}  # 600004 sharpe None、600003 0.5

    def test_exact_subtype_membership_combines_with_predicate(self, db_session):
        """市场链路两层组合：成员判定（精确 subtype IN）+ 阈值谓词 = SQL 全链路"""
        db_session.add_all([
            Fund(code="700001", name="股A", market_subtype="股票型",
                 age_years=6.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
            Fund(code="700002", name="股B", market_subtype="QDII-普通股票",
                 age_years=6.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
            Fund(code="700003", name="股C", market_subtype="混合型-偏债",
                 age_years=6.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
        ])
        db_session.add_all([
            FundRiskMetrics(code="700001", sharpe=1.0, as_of_date=date(2026, 9, 1)),
            FundRiskMetrics(code="700002", sharpe=0.9, as_of_date=date(2026, 9, 1)),
            FundRiskMetrics(code="700003", sharpe=1.1, as_of_date=date(2026, 9, 1)),
        ])
        db_session.commit()

        types = ["股票型", "QDII-普通股票"]  # 精确 akshare 子类（非 UI 粗类别）
        sql_codes = {
            it["code"] for it in FilterService(db_session).screen_discovery_stock(
                market_types=types, min_sharpe=0.8)["items"]
        }
        rows = _collect_predicate_rows(db_session, codes=["700001", "700002", "700003"])
        pred_codes = {
            r.code for r in rows
            if r.market_subtype in types and entry_predicate(min_sharpe=0.8)(r)
        }
        assert sql_codes == pred_codes == {"700001", "700002"}

    def test_coarse_type_string_matches_nothing(self, db_session):
        """contracts §8 的坑：粗类别字符串「QDII」不是精确 subtype，
        两层组合在 SQL 与谓词两侧语义一致（都返回空，不静默展开）"""
        db_session.add_all([
            Fund(code="700001", name="股A", market_subtype="QDII-普通股票",
                 age_years=6.0, size_yi=10.0, mgr_experience_years=8.0, is_active=True),
        ])
        db_session.add(FundRiskMetrics(code="700001", sharpe=0.9,
                                       as_of_date=date(2026, 9, 1)))
        db_session.commit()

        sql = FilterService(db_session).screen_discovery_stock(
            market_types=["QDII"], min_sharpe=0.8)
        assert sql["total"] == 0

        rows = _collect_predicate_rows(db_session, codes=["700001"])
        pred_codes = {
            r.code for r in rows
            if r.market_subtype in ["QDII"] and entry_predicate(min_sharpe=0.8)(r)
        }
        assert pred_codes == set()


# ─────────────────────────────────────────────────────────────
# 步骤 3：dd_3y 冻结接入两条股基链路 + calculated_at 冻结
# ─────────────────────────────────────────────────────────────

class TestDdFreezeIntegration:
    """freeze_dd_rows 在两条股基链路的业绩 commit 后把 dd_3y 合并进 base_rows"""

    def test_stock_refresh_freezes_dd3y(self, db_session, monkeypatch):
        """雪球三分法：主循环 persist+commit 后冻结（_fake_snapshot_ok dd_3y=-5.0）"""
        cap = SharpeRunCapture(run_id="run-dd-s")
        TestStockRefreshCapture()._run_stock_refresh(db_session, monkeypatch, cap)

        assert cap.base_rows["300001"]["dd_3y"] == -5.0
        assert cap.base_rows["300002"]["dd_3y"] == -5.0

    def test_market_pipeline_freezes_dd3y_after_l3(self, db_session, monkeypatch):
        """市场链路：L3 commit 后冻结（mock L3 真实写 FundPerformance.dd_3y=-8.0）"""
        from src.db.models import FundPerformance

        def fake_nav_refresh(db, nav_data, task_id=None):
            for code in nav_data:
                db.merge(FundPerformance(code=code, as_of_date=date(2026, 9, 7), dd_3y=-8.0))
            db.commit()
            return {"task_id": task_id, "total": len(nav_data),
                    "inserted": len(nav_data), "updated": 0, "failed": 0, "errors": []}

        from tests.test_market_full_pipeline import TestRefreshMarketFullSync
        TestRefreshMarketFullSync()._mock_all_fetchers(monkeypatch)
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_nav_db", fake_nav_refresh)
        self_test = TestMarketFullPipelineCapture()
        self_test._seed_stock_universe(db_session)

        cap = SharpeRunCapture(run_id="run-dd-m")
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            refresh_market_full_sync(
                universe_filter=["股票型"], min_ret_3y=20, min_size_yi=5,
                min_mgr_exp=5, preset_task_id="test-cap-dd", capture=cap,
            )

        assert cap.base_rows["300001"]["dd_3y"] == -8.0

    def test_dd_freeze_survives_later_overwrite(self, db_session, monkeypatch):
        """冻结后普通刷新覆盖 FundPerformance，capture 里的 dd_3y 不变"""
        cap = SharpeRunCapture(run_id="run-dd-o")
        TestStockRefreshCapture()._run_stock_refresh(db_session, monkeypatch, cap)
        frozen = cap.base_rows["300001"]["dd_3y"]

        row = db_session.get(FundPerformance, "300001")
        row.dd_3y = -99.0
        db_session.commit()

        assert cap.base_rows["300001"]["dd_3y"] == frozen


class TestCalculatedAtFreeze:
    """risk_rows 冻结指标计算时刻（R7：与样本尾日/刷新日区分）"""

    def test_calculated_at_is_aware_utc_datetime(self, db_session, monkeypatch):
        from datetime import UTC, datetime as dt
        _seed_fund(db_session, "000001")
        db_session.commit()
        monkeypatch.setattr("src.services.risk_service.fetch_nav",
                            lambda code: _nav_df(seed=5))
        cap = SharpeRunCapture(run_id="run-ca")
        refresh_fund_risks(db_session, ["000001"], capture=cap)
        value = cap.risk_rows["000001"]["calculated_at"]
        assert isinstance(value, dt) and value.tzinfo is UTC


# ─────────────────────────────────────────────────────────────
# v2（11-13-sharpe-board-v2-rules）：冻结字段修复 + peer 数据冻结
# ─────────────────────────────────────────────────────────────
from datetime import date as _date, timedelta as _timedelta  # noqa: E402

from src.db.models import FundAchievementRank  # noqa: E402
from src.services.sharpe_capture import (  # noqa: E402
    BASE_ROW_FIELDS,
    PEER_STALE_DAYS,
    _parse_peer_percentile,
    freeze_peer_rows,
)


class TestBaseRowFieldsV2:
    def test_mgr_experience_years_max_in_frozen_fields(self):
        """AC11：修复既有缺陷——冻结字段必须含共管取最长的经理年限列。"""
        assert "mgr_experience_years_max" in BASE_ROW_FIELDS

    def test_freeze_base_row_includes_max_field(self, db_session):
        db_session.add(Fund(
            code="700001", name="老将+新人共管", fund_type="股票型",
            age_years=6.0, size_yi=20.0, mgr_name="老将", mgr_company="某司",
            mgr_days=8000, mgr_experience_years=22.0,
            mgr_experience_years_max=22.0, is_active=True))
        db_session.commit()
        frozen = freeze_base_row(db_session, "700001")
        assert frozen["mgr_experience_years_max"] == 22.0
        assert frozen["mgr_experience_years"] == 22.0


class TestParsePeerPercentile:
    def test_normal(self):
        assert _parse_peer_percentile("278/1951") == 14.2491
        assert _parse_peer_percentile(" 1/5 ") == 20.0
        assert _parse_peer_percentile("2/6") == 33.3333

    def test_invalid_formats_return_none(self):
        for raw in (None, "", "abc", "abc/def", "0/100", "101/100", "-1/100",
                    "10/0", "10/-5", "10/", "/100"):
            assert _parse_peer_percentile(raw) is None, raw


class TestFreezePeerRows:
    """AC5 / design §2：批量冻结，90 天陈旧用数据自带 as_of_date。"""

    TODAY = _date(2026, 11, 13)

    def _ach(self, db, code, raw, as_of):
        db.add(FundAchievementRank(
            code=code, period_kind="阶段业绩", period="近3年",
            ret=1.0, max_dd=-5.0, peer_rank=raw, as_of_date=as_of,
        ))
        db.commit()

    def test_normal_frozen(self, db_session):
        self._ach(db_session, "710001", "278/1951", self.TODAY)
        out = freeze_peer_rows(db_session, ["710001"], today=self.TODAY)
        assert out["710001"]["peer_pct"] == 14.2491
        assert out["710001"]["peer_raw"] == "278/1951"
        assert out["710001"]["as_of"] == "2026-11-13"

    def test_stale_boundary_90_days(self, db_session):
        # 恰好 90 天：保留；91 天：丢弃
        self._ach(db_session, "710002", "10/100",
                  self.TODAY - _timedelta(days=PEER_STALE_DAYS))
        self._ach(db_session, "710003", "10/100",
                  self.TODAY - _timedelta(days=PEER_STALE_DAYS + 1))
        out = freeze_peer_rows(db_session, ["710002", "710003"], today=self.TODAY)
        assert "710002" in out
        assert "710003" not in out

    def test_invalid_rank_and_missing_code_excluded(self, db_session):
        self._ach(db_session, "710004", "abc", self.TODAY)
        out = freeze_peer_rows(db_session, ["710004", "799999"], today=self.TODAY)
        assert out == {}

    def test_wrong_period_not_picked(self, db_session):
        db_session.add(FundAchievementRank(
            code="710005", period_kind="阶段业绩", period="近1年",
            peer_rank="1/100", as_of_date=self.TODAY))
        db_session.commit()
        assert freeze_peer_rows(db_session, ["710005"], today=self.TODAY) == {}

    def test_batch_over_500_codes(self, db_session):
        """500+ codes 分块查询，不触发 SQLite 参数上限报错。"""
        codes = [f"{720000 + i:06d}" for i in range(520)]
        self._ach(db_session, codes[-1], "1/100", self.TODAY)
        out = freeze_peer_rows(db_session, codes, today=self.TODAY)
        assert list(out) == [codes[-1]]

    def test_empty_codes_returns_empty(self, db_session):
        assert freeze_peer_rows(db_session, [], today=self.TODAY) == {}


class TestV2PeerFreezeWiring:
    """design §11：两条链路都在 achievement 落库后冻结 peer_rows。

    11-14 起冻结口径改为年度（v3），字段从 peer_pct 变为年度达标结构。
    """

    def test_stock_chain_freezes_peer_rows(self, db_session, monkeypatch):
        from src.services.sharpe_capture import SharpeRunCapture

        # 预置年度 achievement（模拟 snapshot_fund(fetch_ranking=True) 已写库）
        for year in ("2023", "2024"):
            db_session.add(FundAchievementRank(
                code="300001", period_kind="年度业绩", period=year,
                ret=1.0, max_dd=-5.0, peer_rank="1/10",
                as_of_date=date(2026, 9, 9)))
        db_session.commit()

        helper = TestStockRefreshCapture()
        cap = SharpeRunCapture(run_id="run-v2w1")
        # ref_year 固定到 2026 -> 窗口 2023/2024/2025
        with patch("src.services.sharpe_capture.date") as mock_date:
            mock_date.today.return_value = date(2026, 11, 14)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            helper._run_stock_refresh(db_session, monkeypatch, cap)
        assert cap.peer_rows["300001"]["qualified_years"] == 2
        assert cap.peer_rows["300001"]["qualified"] is True
        assert "300002" not in cap.peer_rows  # 无 achievement 记录的 code 不入字典


# ─────────────────────────────────────────────────────────────
# v3 年度同类排名（11-14-sharpe-board-v3-yearly-peer）
# ─────────────────────────────────────────────────────────────
from src.services.sharpe_capture import (  # noqa: E402
    MIN_YEARLY_TOP_PCT, MIN_YEARLY_YEARS, YEARLY_WINDOW,
    freeze_yearly_peer_rows, yearly_window,
)


class TestYearlyWindow:
    def test_2026_window_excludes_current_year(self):
        assert yearly_window(2026) == ["2023", "2024", "2025"]

    def test_window_rolls_with_year(self):
        assert yearly_window(2027) == ["2024", "2025", "2026"]
        assert yearly_window(2024) == ["2021", "2022", "2023"]

    def test_window_ascending_order(self):
        w = yearly_window(2026)
        assert w == sorted(w), "窗口应升序，展示与断言都依赖顺序"

    def test_defaults_match_profile_constants(self):
        assert YEARLY_WINDOW == 3
        assert MIN_YEARLY_TOP_PCT == 25.0
        assert MIN_YEARLY_YEARS == 2


class TestFreezeYearlyPeerRows:
    """年度排名是历史固定值：不做 as_of 陈旧判断（与 v2 滚动口径的关键差异）。"""

    def _add(self, db, code, year, raw, as_of=_date(2026, 9, 9)):
        db.add(FundAchievementRank(
            code=code, period_kind="年度业绩", period=year,
            ret=1.0, max_dd=-5.0, peer_rank=raw, as_of_date=as_of,
        ))

    def test_all_three_years_top25_qualified(self, db_session):
        for y in ("2023", "2024", "2025"):
            self._add(db_session, "810001", y, "1/100")   # 1% 分位
        db_session.commit()
        out = freeze_yearly_peer_rows(db_session, ["810001"], ref_year=2026)
        it = out["810001"]
        assert it["qualified_years"] == 3
        assert it["qualified"] is True
        assert it["window"] == ["2023", "2024", "2025"]
        assert it["yearly_top_pct"] == 25.0

    def test_two_of_three_years_qualified(self, db_session):
        self._add(db_session, "810002", "2023", "1/100")     # 1% 达标
        self._add(db_session, "810002", "2024", "2/100")     # 2% 达标
        self._add(db_session, "810002", "2025", "80/100")    # 80% 不达标
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810002"], ref_year=2026)["810002"]
        assert it["qualified_years"] == 2
        assert it["qualified"] is True

    def test_only_one_year_qualified(self, db_session):
        self._add(db_session, "810003", "2023", "1/100")
        self._add(db_session, "810003", "2024", "90/100")
        self._add(db_session, "810003", "2025", "95/100")
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810003"], ref_year=2026)["810003"]
        assert it["qualified_years"] == 1
        assert it["qualified"] is False

    def test_missing_year_counts_as_not_qualified(self, db_session):
        """缺年不影响已有年份的判定，但缺失年不能算作达标。"""
        self._add(db_session, "810004", "2023", "1/100")
        self._add(db_session, "810004", "2025", "1/100")
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810004"], ref_year=2026)["810004"]
        assert it["years"]["2024"] is None
        assert it["qualified_years"] == 2
        assert it["qualified"] is True

    def test_boundary_exactly_25_pct_qualified(self, db_session):
        """分位恰好 25.0% 算达标（含等号）。"""
        for y in ("2023", "2024"):
            self._add(db_session, "810005", y, "25/100")   # 25.0%
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810005"], ref_year=2026)["810005"]
        assert it["years"]["2023"] == 25.0
        assert it["qualified_years"] == 2

    def test_just_over_boundary_not_qualified(self, db_session):
        for y in ("2023", "2024"):
            self._add(db_session, "810006", y, "2501/10000")  # 25.01%
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810006"], ref_year=2026)["810006"]
        assert it["years"]["2023"] > 25.0
        assert it["qualified_years"] == 0

    def test_invalid_rank_becomes_none(self, db_session):
        """全部年份格式异常 → 等同无数据，不入字典（发布侧计 gate_missing）。"""
        self._add(db_session, "810007", "2023", "abc")
        self._add(db_session, "810007", "2024", "0/100")
        self._add(db_session, "810007", "2025", "101/100")
        db_session.commit()
        out = freeze_yearly_peer_rows(db_session, ["810007"], ref_year=2026)
        assert out == {}

    def test_partial_invalid_keeps_valid_years(self, db_session):
        """部分年份异常时，无效年记 None，有效年仍参与判定。"""
        self._add(db_session, "810013", "2023", "abc")     # 无效
        self._add(db_session, "810013", "2024", "1/100")    # 达标
        self._add(db_session, "810013", "2025", "2/100")    # 达标
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810013"], ref_year=2026)["810013"]
        assert it["years"]["2023"] is None
        assert it["years"]["2024"] == 1.0
        assert it["qualified_years"] == 2
        assert it["qualified"] is True

    def test_no_data_at_all_excluded_from_dict(self, db_session):
        """窗口内全无有效排名 → 不入字典（无证据，发布侧计诊断）。"""
        out = freeze_yearly_peer_rows(db_session, ["810008"], ref_year=2026)
        assert out == {}

    def test_stale_as_of_still_used(self, db_session):
        """关键差异：年度排名不看 as_of 陈旧度，两年前写入照样有效。"""
        for y in ("2023", "2024"):
            self._add(db_session, "810009", y, "1/100", as_of=_date(2024, 1, 1))
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810009"], ref_year=2026)["810009"]
        assert it["qualified"] is True

    def test_year_outside_window_ignored(self, db_session):
        self._add(db_session, "810010", "2022", "1/100")   # 窗口外
        self._add(db_session, "810010", "2023", "1/100")
        self._add(db_session, "810010", "2024", "1/100")
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810010"], ref_year=2026)["810010"]
        assert "2022" not in it["years"]
        assert it["qualified_years"] == 2

    def test_window_rolls_with_ref_year(self, db_session):
        """ref_year=2027 → 窗口 2024/2025/2026，2023 年数据不再参与。"""
        for y in ("2023", "2024", "2025"):
            self._add(db_session, "810011", y, "1/100")
        db_session.commit()
        it = freeze_yearly_peer_rows(db_session, ["810011"], ref_year=2027)["810011"]
        assert it["window"] == ["2024", "2025", "2026"]
        assert it["years"]["2026"] is None
        assert it["qualified_years"] == 2          # 2024/2025 达标，2026 缺
        assert it["qualified"] is True

    def test_batch_chunks_over_500(self, db_session):
        codes = [f"{830000 + i:06d}" for i in range(520)]
        for y in ("2023", "2024"):
            self._add(db_session, codes[-1], y, "1/100")
        db_session.commit()
        out = freeze_yearly_peer_rows(db_session, codes, ref_year=2026)
        assert codes[-1] in out
        assert len(out) == 1

    def test_custom_threshold_and_min_years(self, db_session):
        for y in ("2023", "2024"):
            self._add(db_session, "810012", y, "15/100")   # 15%
        db_session.commit()
        # 阈值 10% → 都不达标
        strict = freeze_yearly_peer_rows(
            db_session, ["810012"], ref_year=2026, top_pct=10.0, min_years=1)
        assert strict["810012"]["qualified"] is False
        # 阈值 20% + 只要 1 年 → 达标
        loose = freeze_yearly_peer_rows(
            db_session, ["810012"], ref_year=2026, top_pct=20.0, min_years=1)
        assert loose["810012"]["qualified"] is True
        assert loose["810012"]["yearly_top_pct"] == 20.0
        assert loose["810012"]["min_years"] == 1
