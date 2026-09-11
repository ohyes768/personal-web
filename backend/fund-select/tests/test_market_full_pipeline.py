"""
market_full_pipeline 三段预筛 pipeline 单测

验证：
  _load_market_universe 三段 SQL 预过滤（mgr_exp / ret_3y / size_yi）
  MAX_NAV_STALE_DAYS 常量 = 14（端点不暴露 max_nav_stale_days 参数）
  5 阶段流水线（新增 L5 achievement）
  refresh_market_full_sync 新签名（3 用户参数 + 后端常量）
"""
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from src.db.models import Fund, MarketFundRank
from src.services.market_full_pipeline import (
    MAX_NAV_STALE_DAYS,
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

    def test_filter_by_min_ret_3y(self, db_session):
        """L1 业绩字段预筛：min_ret_3y=30 隐式要求 ret_3y >= 30（NULL 排除）"""
        from src.db.models import MarketFundRank
        from datetime import date as _date
        # funds 表记录（必须，否则 EXISTS 子查询无意义）
        for code, ret_3y in [("000001", 50.0), ("000002", 35.0), ("000003", 20.0), ("000004", None)]:
            db_session.add(_mk_fund(code, "股票型"))
            db_session.add(MarketFundRank(
                code=code, nav_date=_date(2026, 9, 7), nav_latest=1.0,
                ret_3y=ret_3y, ft_code="股票型",
            ))
        db_session.commit()

        codes = _load_market_universe(db_session, min_ret_3y=30)
        assert set(codes) == {"000001", "000002"}  # 000003 (20<30) 和 000004 (NULL) 被排除

    def test_filter_by_max_nav_stale_days(self, db_session):
        """L1 字段预筛：max_nav_stale_days=30 排除 nav_date 太老的"""
        from src.db.models import MarketFundRank
        from datetime import date as _date, timedelta as _td
        today = _date(2026, 9, 7)
        for code, days_ago in [("000001", 5), ("000002", 15), ("000003", 60)]:
            db_session.add(_mk_fund(code, "股票型"))
            db_session.add(MarketFundRank(
                code=code, nav_date=today - _td(days=days_ago), nav_latest=1.0,
                ft_code="股票型",
            ))
        db_session.commit()

        codes = _load_market_universe(db_session, max_nav_stale_days=30)
        assert set(codes) == {"000001", "000002"}  # 000003 (60 天前) 被排除

    def test_inactive_excluded(self, db_session):
        db_session.add_all([
            _mk_fund("000001", "股票型", is_active=True),
            _mk_fund("000002", "股票型", is_active=False),
        ])
        db_session.commit()

        codes = _load_market_universe(db_session)
        assert codes == ["000001"]

    # ── 三段预筛新增测试 ─────────────────────────────────────────

    def test_stage1_filter_by_mgr_experience_years(self, db_session):
        """预筛 1：min_mgr_exp=10 排除 mgr_experience_years < 10 的基金"""
        db_session.add_all([
            _mk_fund("000001", "股票型", mgr_experience_years=15.0),
            _mk_fund("000002", "股票型", mgr_experience_years=8.0),
            _mk_fund("000003", "股票型", mgr_experience_years=None),  # NULL 排除
        ])
        db_session.commit()

        codes = _load_market_universe(db_session, min_mgr_exp=10)
        assert codes == ["000001"]

    def test_stage3_filter_by_size_yi(self, db_session):
        """预筛 3：min_size_yi=20 排除 size_yi < 20 的基金"""
        db_session.add_all([
            _mk_fund("000001", "股票型", size_yi=50.0),
            _mk_fund("000002", "股票型", size_yi=15.0),
            _mk_fund("000003", "股票型", size_yi=None),  # NULL 排除
        ])
        db_session.commit()

        codes = _load_market_universe(db_session, min_size_yi=20)
        assert codes == ["000001"]

    def test_combined_three_stage_filters(self, db_session):
        """三段预筛全部生效：mgr_exp + ret_3y + size_yi"""
        from src.db.models import MarketFundRank
        from datetime import date as _date
        # 000001: 三段都过
        # 000002: mgr_exp < 5  → 预筛 1 排除
        # 000003: ret_3y < 20 → 预筛 2 排除
        # 000004: size_yi < 10 → 预筛 3 排除
        db_session.add_all([
            _mk_fund("000001", "股票型", mgr_experience_years=10.0, size_yi=30.0),
            _mk_fund("000002", "股票型", mgr_experience_years=3.0, size_yi=30.0),
            _mk_fund("000003", "股票型", mgr_experience_years=10.0, size_yi=30.0),
            _mk_fund("000004", "股票型", mgr_experience_years=10.0, size_yi=5.0),
        ])
        db_session.add_all([
            MarketFundRank(code="000001", nav_date=_date(2026, 9, 7),
                           nav_latest=1.0, ret_3y=25.0, ft_code="股票型"),
            MarketFundRank(code="000002", nav_date=_date(2026, 9, 7),
                           nav_latest=1.0, ret_3y=25.0, ft_code="股票型"),
            MarketFundRank(code="000003", nav_date=_date(2026, 9, 7),
                           nav_latest=1.0, ret_3y=15.0, ft_code="股票型"),
            MarketFundRank(code="000004", nav_date=_date(2026, 9, 7),
                           nav_latest=1.0, ret_3y=25.0, ft_code="股票型"),
        ])
        db_session.commit()

        codes = _load_market_universe(
            db_session,
            min_mgr_exp=5, min_ret_3y=20, min_size_yi=10,
            max_nav_stale_days=MAX_NAV_STALE_DAYS,
        )
        assert codes == ["000001"]

    def test_max_nav_stale_days_constant_is_14(self):
        """常量 = 14（A 股工作日 5/周 + 节假日 buffer）"""
        assert MAX_NAV_STALE_DAYS == 14


class TestRefreshMarketFullSyncSignature:

    def test_accepts_three_user_params_plus_task_id(self):
        """新签名：universe_filter + 3 用户参数 + preset_task_id"""
        import inspect
        sig = inspect.signature(refresh_market_full_sync)
        params = list(sig.parameters.keys())
        assert params == [
            "universe_filter",
            "min_ret_3y",
            "min_size_yi",
            "min_mgr_exp",
            "preset_task_id",
            "pipeline_profile",
        ], f"签名变更：新增 pipeline_profile；当前参数: {params}"

    def test_no_longer_accepts_min_ret_1y_or_max_nav_stale_days(self):
        """旧参数被移除：min_ret_1y / max_nav_stale_days"""
        import inspect
        sig = inspect.signature(refresh_market_full_sync)
        assert "min_ret_1y" not in sig.parameters
        assert "max_nav_stale_days" not in sig.parameters


class TestRefreshMarketFullSync:
    def _mock_all_fetchers(self, monkeypatch):
        """mock 6 个 fetcher 避免网络调用（patch module 顶部 import 的引用）"""
        import pandas as pd
        from datetime import date
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_universe",
            lambda: pd.DataFrame([{
                "code": "000001", "name": "X", "market_subtype": "股票型",
                "market_type": "stock",
            }]),
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_universe_db",
            lambda db, df, task_id=None: {"task_id": task_id, "total": len(df),
                                                 "inserted": len(df), "updated": 0, "failed": 0, "errors": []},
        )
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
            "src.services.market_full_pipeline.fetch_market_size",
            lambda codes, **kw: [
                {"code": c, "established_date": date(2020, 1, 1),
                 "age_years": 6.0, "size_yi": 25.0, "mgr_company": "公司"}
                for c in codes
            ],
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_nav",
            lambda codes, **kw: {c: pd.DataFrame({"净值日期": [date(2026, 9, 7)], "单位净值": [1.0], "日增长率": [0.1]}) for c in codes},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_achievement",
            lambda codes, **kw: {},  # 模拟无同类排名数据
        )
        # refresh 函数
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_rank_db",
            lambda db, df, task_id=None: {"task_id": task_id, "total": len(df),
                                              "inserted": len(df), "updated": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_size_db",
            lambda db, rows, task_id=None: {"task_id": task_id, "total": len(rows),
                                                 "inserted": 0, "updated": len(rows), "failed": 0, "errors": []},
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
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_achievement",
            lambda db, ach_data, task_id=None: {"task_id": task_id, "total": len(ach_data),
                                                    "inserted": len(ach_data), "failed": 0, "errors": []},
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
        from src.db.models import MarketFundRank
        from datetime import date as _date
        db_session.add_all([
            _mk_fund("000001", "股票型", size_yi=20, age_years=5),
            _mk_fund("000002", "股票型", size_yi=30, age_years=8),
        ])
        # 必须给两基金加 market_fund_rank 业绩，否则 EXISTS 子查询排除
        for code in ("000001", "000002"):
            db_session.add(MarketFundRank(
                code=code, nav_date=_date(2026, 9, 7), nav_latest=1.0,
                ret_3y=20.0, ft_code="股票型",
            ))
        db_session.commit()

        call_log = []
        self._mock_all_fetchers(monkeypatch)

        # 在 mock refresh_*_db 内部记录调用顺序
        import src.services.market_full_pipeline as mfp
        original_rank = mfp.refresh_market_rank_db
        original_size = mfp.refresh_market_size_db
        original_nav = mfp.refresh_market_nav_db
        original_risk = mfp.refresh_market_risk_db

        def rank_with_log(db, df, task_id=None):
            call_log.append("L1_refresh")
            return original_rank(db, df, task_id)
        def size_with_log(db, rows, task_id=None):
            call_log.append("L2_refresh")
            return original_size(db, rows, task_id)
        def nav_with_log(db, nav_data, task_id=None):
            call_log.append("L3_refresh")
            return original_nav(db, nav_data, task_id)
        def risk_with_log(db, codes, task_id=None):
            call_log.append("L4_refresh")
            return original_risk(db, codes, task_id)

        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_rank_db", rank_with_log)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_size_db", size_with_log)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_nav_db", nav_with_log)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_risk_db", risk_with_log)

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(
                universe_filter=["股票型"],
                min_ret_3y=0,
                preset_task_id="test-pipeline",
            )

        assert result["task_id"] == "test-pipeline"
        assert result["universe_size"] == 2

        # 6 阶段都 done：L0_universe / L1_rank / L2_size / L3_nav / L4_risk / L5_achievement
        for stage in ("L0_universe", "L1_rank", "L2_size", "L3_nav", "L4_risk", "L5_achievement"):
            assert result["stage_results"][stage]["status"] == "done", f"{stage} not done"

        # 顺序：L0 → L1 → L2 → L3 → L4（call_log 只记 refresh 阶段，不含 L0 fetch_universe 和 L5 achievement；后者 mock 返回空 dict）
        assert call_log == ["L1_refresh", "L2_refresh", "L3_refresh", "L4_refresh"]

    def test_single_stage_failure_does_not_block_others(self, db_session, monkeypatch):
        """L2 失败时 L3/L4 仍继续"""
        db_session.add(_mk_fund("000001", "股票型", size_yi=20, age_years=5))
        db_session.commit()

        self._mock_all_fetchers(monkeypatch)
        # L2 故意失败
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_size_db",
            lambda db, rows, task_id=None: (_ for _ in ()).throw(RuntimeError("L2 boom")),
        )
        # L2 的 fetcher 也失败
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_size",
            lambda codes, **kw: (_ for _ in ()).throw(RuntimeError("L2 boom")),
        )

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(universe_filter=["股票型"], preset_task_id="test-fail")

        assert result["stage_results"]["L1_rank"]["status"] == "done"
        assert result["stage_results"]["L2_size"]["status"] == "error"
        assert result["stage_results"]["L3_nav"]["status"] == "done"
        assert result["stage_results"]["L4_risk"]["status"] == "done"
        # L0 universe 在最前面跑过，状态应是 done（除非 L2 影响整体）
        assert result["stage_results"]["L0_universe"]["status"] == "done"

    def test_codes_recomputed_after_each_stage(self, db_session, monkeypatch):
        """分阶段重算 codes：清库场景下 size_yi 全空时仍能命中

        场景：
          - funds 表 mgr_* 已填，size_yi 全空（首次清库跑）
          - market_fund_rank 表空
          - 预筛参数：min_ret_3y=20 / min_size_yi=5 / min_mgr_exp=5
          - mock L1 真实写入 market_fund_rank 表（L1 后预筛 2 能命中）
          - mock L2 真实更新 funds.size_yi（L2 后预筛 3 能命中）
          - 期望最终 codes 非空
        """
        from datetime import date as _date
        import pandas as _pd
        from src.db.models import MarketFundRank, Fund
        # 4 只基金：mgr_exp + size_yi 状态各异
        funds = [
            ("000001", 10.0, None),   # mgr_exp 10 + 业绩后 size=30 → 命中
            ("000002", 3.0,  None),   # mgr_exp 3 → 预筛 1 排除
            ("000003", 10.0, None),   # mgr_exp 10 + 业绩后 size=2 → 预筛 3 排除
            ("000004", 10.0, None),   # mgr_exp 10 + 业绩后 size=10 → 命中
        ]
        for code, mgr_exp, size in funds:
            db_session.add(_mk_fund(code, "股票型", mgr_experience_years=mgr_exp, size_yi=size))
        db_session.commit()

        # mock L0 universe fetch（关键：必须 patch L0 内部 import 的版本）
        monkeypatch.setattr(
            "src.data.market_universe_fetcher.fetch_market_universe",
            lambda: _pd.DataFrame([{
                "code": "000001", "name": "X", "market_subtype": "股票型", "market_type": "stock",
            }]),
        )
        # mock L1 rank fetch（只返回 mgr_exp>=5 的 3 只，避免 fake_rank 跑无关行）
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_rank_bulk",
            lambda symbols=None, **kw: _pd.DataFrame([{
                "code": "000001", "name": "X", "nav_date": _date(2026, 9, 7),
                "nav_latest": 1.5, "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                "ret_6m": 6.0, "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 40.0,
                "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp",
            }, {
                "code": "000003", "name": "X", "nav_date": _date(2026, 9, 7),
                "nav_latest": 1.5, "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                "ret_6m": 6.0, "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 35.0,
                "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp",
            }, {
                "code": "000004", "name": "X", "nav_date": _date(2026, 9, 7),
                "nav_latest": 1.5, "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                "ret_6m": 6.0, "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 30.0,
                "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp",
            }]),
        )

        # mock L1 refresh：真实写 MarketFundRank（让预筛 2 命中）
        def fake_rank_refresh(db, df, task_id=None):
            inserted = 0
            for row in df.to_dict("records"):
                db.add(MarketFundRank(
                    code=row["code"],
                    nav_date=_date(2026, 9, 7),
                    nav_latest=1.0,
                    ret_3y=row.get("ret_3y", 25.0),
                    ft_code="gp",
                ))
                inserted += 1
            db.commit()
            return {"task_id": task_id, "total": len(df), "inserted": inserted, "updated": 0, "failed": 0, "errors": []}

        # mock L2 refresh：真实更新 Fund.size_yi（让预筛 3 能命中）
        def fake_size_refresh(db, rows, task_id=None):
            updated = 0
            for r in rows:
                code = r["code"]
                fake_size = {"000001": 30.0, "000003": 2.0, "000004": 10.0}.get(code)
                if fake_size is not None:
                    fund = db.query(Fund).filter_by(code=code).one()
                    fund.size_yi = fake_size
                    updated += 1
            db.commit()
            return {"task_id": task_id, "total": len(rows), "inserted": 0, "updated": updated, "failed": 0, "errors": []}

        # 用 _mock_all_fetchers 先 mock 其他 fetcher 和 refresh
        self._mock_all_fetchers(monkeypatch)
        # **之后**再覆盖 fetch_market_rank_bulk + refresh_market_rank_db + refresh_market_size_db
        # （_mock_all_fetchers 已经 mock 了这些，但我们要让 fake 真正写 DB 让后续 _load_market_universe 能看到）
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_rank_bulk",
            lambda symbols=None, **kw: _pd.DataFrame([
                {"code": "000001", "name": "X", "nav_date": _date(2026, 9, 7),
                 "nav_latest": 1.5, "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                 "ret_6m": 6.0, "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 40.0,
                 "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp"},
                {"code": "000003", "name": "X", "nav_date": _date(2026, 9, 7),
                 "nav_latest": 1.5, "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                 "ret_6m": 6.0, "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 35.0,
                 "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp"},
                {"code": "000004", "name": "X", "nav_date": _date(2026, 9, 7),
                 "nav_latest": 1.5, "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                 "ret_6m": 6.0, "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 30.0,
                 "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp"},
            ]),
        )
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_rank_db", fake_rank_refresh)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_size_db", fake_size_refresh)

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(
                universe_filter=["股票型"],
                min_ret_3y=20,
                min_size_yi=5,
                min_mgr_exp=5,
                preset_task_id="test-recompute",
            )

        # 最终 universe_size 应为 2（000001 + 000004 命中三段预筛）
        assert result["universe_size"] == 2, f"分阶段重算后 universe 应为 2 只，实际 {result['universe_size']}"

        # 所有阶段 done
        for stage in ("L0_universe", "L1_rank", "L2_size", "L3_nav", "L4_risk", "L5_achievement"):
            assert result["stage_results"][stage]["status"] == "done", f"{stage} not done"


class TestPipelineProfile:
    """pipeline_profile 参数决定跑 6 阶段（stock）还是 4 阶段（bond）。"""

    def _mock_all_fetchers(self, monkeypatch):
        """复用 TestRefreshMarketFullSync 的 mock 集合（避免重新抄一遍）"""
        from tests.test_market_full_pipeline import TestRefreshMarketFullSync
        TestRefreshMarketFullSync()._mock_all_fetchers(monkeypatch)

    def _seed_funds(self, db_session):
        """注入 2 只债券型 + 1 只股票型 universe，让 _load_market_universe 返回非空"""
        from src.db.models import MarketFundRank
        from datetime import date
        db_session.add_all([
            _mk_fund("000001", "债券型-中短债", size_yi=10, is_active=True),
            _mk_fund("000002", "债券型-长期纯债", size_yi=10, is_active=True),
            _mk_fund("000003", "股票型", size_yi=10, is_active=True),
        ])
        # 给 000001/000002/000003 写入 nav_date + ret_3y（让 L1 后预筛 2 不把它们都砍掉）
        # MarketFundRank 没有 name 列
        db_session.add_all([
            MarketFundRank(code="000001", nav_date=date(2026, 9, 7), ret_3y=20.0,
                           ret_1w=0.5, ret_1m=1.0, ret_3m=3.0,
                           ret_6m=6.0, ret_1y=12.0, ret_2y=25.0, ret_ytd=8.0,
                           ret_all=60.0, ft_code="gp"),
            MarketFundRank(code="000002", nav_date=date(2026, 9, 7), ret_3y=20.0,
                           ret_1w=0.5, ret_1m=1.0, ret_3m=3.0,
                           ret_6m=6.0, ret_1y=12.0, ret_2y=25.0, ret_ytd=8.0,
                           ret_all=60.0, ft_code="gp"),
            MarketFundRank(code="000003", nav_date=date(2026, 9, 7), ret_3y=20.0,
                           ret_1w=0.5, ret_1m=1.0, ret_3m=3.0,
                           ret_6m=6.0, ret_1y=12.0, ret_2y=25.0, ret_ytd=8.0,
                           ret_all=60.0, ft_code="gp"),
        ])
        db_session.commit()

    def test_bond_profile_skips_l4_and_l5(self, db_session, monkeypatch):
        """profile='bond' → stage_results 仅含 L0/L1/L2/L3；L4/L5 key 不存在"""
        self._mock_all_fetchers(monkeypatch)
        self._seed_funds(db_session)

        # 故意把 L4/L5 标记为"调用即炸"，确保不被调用
        l4_called = {"flag": False}
        l5_called = {"flag": False}

        def fake_risk(db, codes, task_id=None):
            l4_called["flag"] = True
            return {"task_id": task_id, "total": len(codes), "completed": len(codes), "failed": 0, "errors": []}

        def fake_achievement(db, ach_data, task_id=None):
            l5_called["flag"] = True
            return {"task_id": task_id, "total": len(ach_data), "inserted": len(ach_data), "failed": 0, "errors": []}

        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_risk_db", fake_risk)
        monkeypatch.setattr("src.services.market_full_pipeline.refresh_market_achievement", fake_achievement)

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(
                universe_filter=["债券型-中短债", "债券型-长期纯债"],
                pipeline_profile="bond",
                preset_task_id="test-bond-profile",
            )

        # 阶段：只跑 4 个
        assert set(result["stage_results"].keys()) == {"L0_universe", "L1_rank", "L2_size", "L3_nav"}, \
            f"bond profile 应只跑 4 阶段，实际 {set(result['stage_results'].keys())}"

        # L4/L5 不能被调用
        assert l4_called["flag"] is False, "L4 risk refresh 不该被调用"
        assert l5_called["flag"] is False, "L5 achievement refresh 不该被调用"

        # 状态：main task 标记 done
        from src.db.models import RefreshRun
        run = db_session.get(RefreshRun, "test-bond-profile")
        assert run.status == "done"
        assert run.total == run.universe_size * 4 if hasattr(run, "universe_size") else run.total >= 4

    def test_default_profile_runs_all_six_stages(self, db_session, monkeypatch):
        """不传 pipeline_profile → 默认 stock，6 阶段全跑（回归保护）"""
        self._mock_all_fetchers(monkeypatch)
        self._seed_funds(db_session)

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result = refresh_market_full_sync(
                universe_filter=["股票型"],
                preset_task_id="test-default-profile",
            )

        expected = {"L0_universe", "L1_rank", "L2_size", "L3_nav", "L4_risk", "L5_achievement"}
        assert set(result["stage_results"].keys()) == expected, \
            f"默认 profile 应跑 6 阶段，实际 {set(result['stage_results'].keys())}"

    def test_invalid_profile_raises_value_error(self, db_session, monkeypatch):
        """pipeline_profile='xxx' → ValueError 早抛，不进 pipeline"""
        from src.db.models import RefreshRun
        self._mock_all_fetchers(monkeypatch)
        self._seed_funds(db_session)

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            with pytest.raises(ValueError, match="pipeline_profile must be 'stock' or 'bond'"):
                refresh_market_full_sync(
                    universe_filter=["股票型"],
                    pipeline_profile="etf",
                    preset_task_id="test-bad-profile",
                )

        # 不应创建 RefreshRun
        run = db_session.get(RefreshRun, "test-bad-profile")
        assert run is None, "非法 profile 不该写 RefreshRun 记录"

    def test_main_run_total_reflects_stages_per_code(self, db_session, monkeypatch):
        """main_run.total = codes × stages_per_code（stock=6, bond=4）"""
        from src.db.models import RefreshRun
        self._mock_all_fetchers(monkeypatch)
        self._seed_funds(db_session)

        # 跑 bond profile
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result_bond = refresh_market_full_sync(
                universe_filter=["债券型-中短债", "债券型-长期纯债"],
                pipeline_profile="bond",
                preset_task_id="test-total-bond",
            )
        run_bond = db_session.get(RefreshRun, "test-total-bond")
        assert run_bond.total == result_bond["universe_size"] * 4, \
            f"bond profile total 应为 universe × 4，实际 {run_bond.total} vs {result_bond['universe_size']}×4"

        # 跑 stock profile
        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            result_stock = refresh_market_full_sync(
                universe_filter=["股票型"],
                pipeline_profile="stock",
                preset_task_id="test-total-stock",
            )
        run_stock = db_session.get(RefreshRun, "test-total-stock")
        assert run_stock.total == result_stock["universe_size"] * 6, \
            f"stock profile total 应为 universe × 6，实际 {run_stock.total} vs {result_stock['universe_size']}×6"
