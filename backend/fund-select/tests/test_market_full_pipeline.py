"""
market_full_pipeline 4 阶段 pipeline 单测

验证：
  _load_market_universe SQL 预过滤
  4 阶段依次执行
  单阶段失败不阻塞后续阶段
"""
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from src.db.models import Fund, MarketFundRank
from src.services.market_full_pipeline import (
    _load_market_universe,
    refresh_market_full_sync,
)


def _mk_fund(code: str, market_subtype: str, **kw):
    """测试基金工厂"""
    defaults = dict(
        code=code, name=f"基金{code}", market_subtype=market_subtype,
        market_type="bond" if "债" in market_subtype else "stock",
        fund_type="中长期纯债" if "债" in market_subtype else "股票型",
        age_years=kw.pop("age_years", 5.0),
        size_yi=kw.pop("size_yi", 10.0),
        is_active=kw.pop("is_active", True),
    )
    defaults.update(kw)
    return Fund(**defaults)


class TestLoadMarketUniverse:
    def test_no_filter_returns_all(self, db_session):
        db_session.add_all([
            _mk_fund("000001", "债券型-中短债", size_yi=5),
            _mk_fund("000002", "股票型", size_yi=20),
            _mk_fund("000003", "QDII-普通股票", size_yi=100),
            _mk_fund("000004", "FOF-稳健型", size_yi=50),  # 不在 universe
        ])
        db_session.commit()

        codes = _load_market_universe(db_session)
        # bond + stock universe 共 3 只（FOF 排除）
        assert set(codes) == {"000001", "000002", "000003"}

    def test_filter_by_market_subtypes(self, db_session):
        db_session.add_all([
            _mk_fund("000001", "债券型-中短债"),
            _mk_fund("000002", "股票型"),
            _mk_fund("000003", "QDII-普通股票"),
        ])
        db_session.commit()

        codes = _load_market_universe(db_session, universe_filter=["股票型"])
        assert codes == ["000002"]

    def test_filter_by_min_size_yi(self, db_session):
        db_session.add_all([
            _mk_fund("000001", "股票型", size_yi=5),
            _mk_fund("000002", "股票型", size_yi=20),
            _mk_fund("000003", "股票型", size_yi=100),
        ])
        db_session.commit()

        codes = _load_market_universe(db_session, min_size_yi=10)
        assert set(codes) == {"000002", "000003"}

    def test_filter_by_min_age(self, db_session):
        db_session.add_all([
            _mk_fund("000001", "股票型", age_years=1),
            _mk_fund("000002", "股票型", age_years=5),
            _mk_fund("000003", "股票型", age_years=10),
        ])
        db_session.commit()

        codes = _load_market_universe(db_session, min_age=3)
        assert set(codes) == {"000002", "000003"}

    def test_inactive_excluded(self, db_session):
        db_session.add_all([
            _mk_fund("000001", "股票型", is_active=True),
            _mk_fund("000002", "股票型", is_active=False),
        ])
        db_session.commit()

        codes = _load_market_universe(db_session)
        assert codes == ["000001"]


class TestRefreshMarketFullSync:
    def _mock_all_fetchers(self, monkeypatch):
        """mock 4 个 fetcher 避免网络调用（patch module 顶部 import 的引用）"""
        import pandas as pd
        from datetime import date
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_rank_bulk",
            lambda symbols=None, **kw: pd.DataFrame([{
                "code": "000001", "name": "X", "nav_date": date(2026, 9, 7),
                "nav_latest": 1.5, "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                "ret_6m": 6.0, "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 40.0,
                "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp",
            }]),
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_basic",
            lambda codes, **kw: pd.DataFrame([{
                "code": c, "name": f"X{c}", "fund_type": "股票型",
                "established_date": date(2020, 1, 1), "age_years": 6.0,
                "size_yi": 25.0, "mgr_name": "经理", "mgr_company": "公司",
                "mgr_days": 365 * 3, "mgr_experience_years": 3.0,
            } for c in codes]),
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_nav",
            lambda codes, **kw: {c: pd.DataFrame({"净值日期": [date(2026, 9, 7)], "单位净值": [1.0], "日增长率": [0.1]}) for c in codes},
        )
        # refresh 函数
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_rank_db",
            lambda db, df, task_id=None: {"task_id": task_id, "total": len(df),
                                              "inserted": len(df), "updated": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_basic_db",
            lambda db, df, task_id=None: {"task_id": task_id, "total": len(df),
                                              "inserted": 0, "updated": len(df), "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_nav_db",
            lambda db, nav_data, task_id=None: {"task_id": task_id, "total": len(nav_data),
                                                   "inserted": len(nav_data), "updated": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_risk_db",
            lambda db, codes, task_id=None: {"task_id": task_id, "total": len(codes),
                                                 "completed": len(codes), "failed": 0, "errors": []},
        )

    def test_empty_universe_returns_early(self, db_session, monkeypatch):
        """universe 为空时各阶段都跳过"""
        self._mock_all_fetchers(monkeypatch)
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(preset_task_id="test-empty")
        assert result["universe_size"] == 0
        assert "L1_rank" in result["stage_results"]
        assert "L4_risk" in result["stage_results"]
        # 空 universe 阶段标记 done
        assert result["stage_results"]["L1_rank"]["status"] == "done"

    def test_pipeline_4_stages_run_in_order(self, db_session, monkeypatch):
        db_session.add_all([
            _mk_fund("000001", "股票型", size_yi=20, age_years=5),
            _mk_fund("000002", "股票型", size_yi=30, age_years=8),
        ])
        db_session.commit()

        call_log = []
        self._mock_all_fetchers(monkeypatch)

        # 在 mock refresh_*_db 内部记录调用顺序
        import src.services.market_full_pipeline as mfp
        original_rank = mfp.refresh_market_rank_db
        original_basic = mfp.refresh_market_basic_db
        original_nav = mfp.refresh_market_nav_db
        original_risk = mfp.refresh_market_risk_db

        def rank_with_log(db, df, task_id=None):
            call_log.append("L1_refresh")
            return original_rank(db, df, task_id)
        def basic_with_log(db, df, task_id=None):
            call_log.append("L2_refresh")
            return original_basic(db, df, task_id)
        def nav_with_log(db, nav_data, task_id=None):
            call_log.append("L3_refresh")
            return original_nav(db, nav_data, task_id)
        def risk_with_log(db, codes, task_id=None):
            call_log.append("L4_refresh")
            return original_risk(db, codes, task_id)

        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_rank_db", rank_with_log)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_basic_db", basic_with_log)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_nav_db", nav_with_log)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_risk_db", risk_with_log)

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(
                universe_filter=["股票型"],
                min_size_yi=10,
                preset_task_id="test-pipeline",
            )

        assert result["task_id"] == "test-pipeline"
        assert result["universe_size"] == 2

        # 4 阶段都 done
        for stage in ("L1_rank", "L2_basic", "L3_nav", "L4_risk"):
            assert result["stage_results"][stage]["status"] == "done", f"{stage} not done"

        # 顺序：L1 → L2 → L3 → L4
        assert call_log == ["L1_refresh", "L2_refresh", "L3_refresh", "L4_refresh"]

    def test_single_stage_failure_does_not_block_others(self, db_session, monkeypatch):
        """L2 失败时 L3/L4 仍继续"""
        db_session.add(_mk_fund("000001", "股票型", size_yi=20, age_years=5))
        db_session.commit()

        self._mock_all_fetchers(monkeypatch)
        # L2 故意失败
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_basic_db",
            lambda db, df, task_id=None: (_ for _ in ()).throw(RuntimeError("L2 boom")),
        )
        # L2 的 fetcher 也失败
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_basic",
            lambda codes, **kw: (_ for _ in ()).throw(RuntimeError("L2 boom")),
        )

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(universe_filter=["股票型"], preset_task_id="test-fail")

        assert result["stage_results"]["L1_rank"]["status"] == "done"
        assert result["stage_results"]["L2_basic"]["status"] == "error"
        assert result["stage_results"]["L3_nav"]["status"] == "done"
        assert result["stage_results"]["L4_risk"]["status"] == "done"
