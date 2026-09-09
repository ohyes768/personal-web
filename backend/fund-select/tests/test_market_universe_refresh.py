"""
全市场基金名单 refresh 单测（in-memory SQLite + conftest 的 db_session）

关键回归点：
- 已存在基金：仅更新 name / market_subtype / market_type，保留 fund_type / is_active
- 新增基金：fund_type 留空、is_active=True
- 进度写入 RefreshRun
"""
from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from src.db.models import Fund, RefreshRun
from src.services.market_universe_refresh import refresh as refresh_market_universe


def _df(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    """构造 fetcher 返回的 DataFrame：code / name / market_subtype / market_type。"""
    return pd.DataFrame(rows, columns=["code", "name", "market_subtype", "market_type"])


def _df_with_ft(rows: list[tuple[str, str, str, str, str]]) -> pd.DataFrame:
    """构造带 fund_type 列的 DataFrame：code / name / market_subtype / market_type / fund_type。"""
    return pd.DataFrame(rows, columns=["code", "name", "market_subtype", "market_type", "fund_type"])


# ── 阶段 0（09-08）扩展：fund_type / mgr_* 写入 ────────────────────────────────


class TestRefreshMarketUniverseStage0:
    """阶段 0：refresh() 同步写入 fund_type / mgr_name / mgr_company / mgr_days /
    mgr_experience_years（数据源：ak.fund_name_em() + ak.fund_manager_em()）。
    """

    def _mgr_by_code(
        self,
        rows: list[tuple[str, str, str, int]],
    ) -> dict[str, list[dict]]:
        """构造 mgr_by_code 字典：rows = [(code, name, company, days), ...]"""
        result: dict[str, list[dict]] = {}
        for code, name, company, days in rows:
            result.setdefault(code, []).append(
                {"name": name, "company": company, "days": days}
            )
        return result

    def test_insert_new_writes_fund_type_and_mgr_fields(self, db_session):
        """新增基金时 fund_type / mgr_* 全部从入参写入。"""
        df = _df_with_ft([
            ("000001", "华夏成长", "股票型", "stock", "股票型"),
            ("000003", "易方达债", "债券型-中短债", "bond", "债券型-中短债"),
        ])
        mgr_by_code = self._mgr_by_code([
            ("000001", "陈染", "华夏基金", 2000),
            ("000003", "缪扬帆", "易方达基金", 3000),
        ])
        result = refresh_market_universe(db_session, df, mgr_by_code=mgr_by_code)
        assert result["inserted"] == 2

        f1 = db_session.get(Fund, "000001")
        assert f1.fund_type == "股票型"
        assert f1.mgr_name == "陈染"
        assert f1.mgr_company == "华夏基金"
        assert f1.mgr_days == 2000
        assert f1.mgr_experience_years == round(2000 / 365.25, 2)

        f3 = db_session.get(Fund, "000003")
        assert f3.fund_type == "债券型-中短债"
        assert f3.mgr_name == "缪扬帆"
        assert f3.mgr_company == "易方达基金"
        assert f3.mgr_days == 3000

    def test_update_existing_preserves_nonempty_fund_type(self, db_session):
        """关键不变量：已有 fund_type='中长期纯债'（老 L2 雪球写入），不被阶段 0 覆盖。"""
        db_session.add(Fund(
            code="000001", name="老基金", fund_type="中长期纯债",
            is_active=True, age_years=5.0,
        ))
        db_session.commit()

        df = _df_with_ft([("000001", "改名", "债券型-长期纯债", "bond", "债券型-长期纯债")])
        refresh_market_universe(db_session, df, mgr_by_code={})

        f = db_session.get(Fund, "000001")
        assert f.fund_type == "中长期纯债"        # 保留
        assert f.name == "改名"                   # name 仍覆盖
        assert f.market_subtype == "债券型-长期纯债"
        # mgr_* 字段原为 None/空（老 L2 没填），传入 mgr_by_code={} 时保持 None
        assert f.mgr_name is None
        assert f.mgr_days is None

    def test_update_existing_writes_fund_type_when_previously_empty(self, db_session):
        """已有 fund_type='' 的行，阶段 0 的 fund_type 会被写入。"""
        db_session.add(Fund(code="000001", name="新基金", fund_type="", is_active=True))
        db_session.commit()

        df = _df_with_ft([("000001", "新基金改名", "股票型", "stock", "股票型")])
        refresh_market_universe(db_session, df, mgr_by_code={})

        f = db_session.get(Fund, "000001")
        assert f.fund_type == "股票型"

    def test_multi_manager_join_and_min_days(self, db_session):
        """多经理：name 用 `、` 拼接；days 取 min（保守估计）；company 取首位。"""
        df = _df_with_ft([("000001", "双经理基金", "混合型-灵活", "stock", "混合型-灵活")])
        mgr_by_code = self._mgr_by_code([
            ("000001", "陈染", "华夏基金", 5000),    # 老将
            ("000001", "缪扬帆", "易方达基金", 1000),  # 新人 → min 取 1000
        ])
        refresh_market_universe(db_session, df, mgr_by_code=mgr_by_code)

        f = db_session.get(Fund, "000001")
        assert f.mgr_name == "陈染、缪扬帆"   # 按 mgr_by_code list 顺序
        assert f.mgr_company == "华夏基金"      # 第一位
        assert f.mgr_days == 1000              # min
        assert f.mgr_experience_years == round(1000 / 365.25, 2)

    def test_update_existing_with_mgr_writes_mgr_only_keeps_fund_type(self, db_session):
        """已有行同时有 fund_type（不覆盖）+ mgr_by_code 提供 mgr（写入）。"""
        db_session.add(Fund(
            code="000001", name="老基金", fund_type="中长期纯债",
            is_active=True, mgr_name="旧经理",
        ))
        db_session.commit()

        df = _df_with_ft([("000001", "改名", "债券型-长期纯债", "bond", "债券型-长期纯债")])
        mgr_by_code = self._mgr_by_code([("000001", "陈染", "华夏基金", 2000)])
        refresh_market_universe(db_session, df, mgr_by_code=mgr_by_code)

        f = db_session.get(Fund, "000001")
        assert f.fund_type == "中长期纯债"   # 不覆盖
        assert f.mgr_name == "陈染"           # 覆盖 mgr_*
        assert f.mgr_company == "华夏基金"
        assert f.mgr_days == 2000

    def test_no_mgr_data_leaves_mgr_fields_none(self, db_session):
        """mgr_by_code 中没有该 code → mgr_* 写 None（不写入 DB，等同保持 None）。"""
        df = _df_with_ft([("000001", "无经理基金", "股票型", "stock", "股票型")])
        mgr_by_code = self._mgr_by_code([("000002", "另一经理", "他基金", 100)])  # 不含 000001
        refresh_market_universe(db_session, df, mgr_by_code=mgr_by_code)

        f = db_session.get(Fund, "000001")
        assert f.fund_type == "股票型"
        assert f.mgr_name is None
        assert f.mgr_company is None
        assert f.mgr_days is None
        assert f.mgr_experience_years is None

    def test_empty_mgr_company_falls_back_to_none(self, db_session):
        """akshare 经理公司为空字符串时，mgr_company 写 None（不写空串）。"""
        df = _df_with_ft([("000001", "无公司基金", "股票型", "stock", "股票型")])
        mgr_by_code = self._mgr_by_code([("000001", "陈染", "", 2000)])
        refresh_market_universe(db_session, df, mgr_by_code=mgr_by_code)

        f = db_session.get(Fund, "000001")
        assert f.mgr_name == "陈染"
        assert f.mgr_company is None
        assert f.mgr_days == 2000

    def test_backward_compatible_signature_no_mgr_writes(self, db_session):
        """老调用方不传 mgr_by_code → 不写 mgr_*（保持向后兼容）。"""
        df = _df_with_ft([("000001", "测试", "股票型", "stock", "股票型")])
        # 不传 mgr_by_code
        refresh_market_universe(db_session, df)

        f = db_session.get(Fund, "000001")
        assert f.fund_type == "股票型"
        assert f.mgr_name is None          # 不写
        assert f.mgr_days is None          # 不写

    def test_df_without_fund_type_column_skips_fund_type_writes(self, db_session):
        """df 不含 fund_type 列 → 不写 fund_type 字段（兼容旧调用方）。"""
        df = _df([("000001", "测试", "股票型", "stock")])  # 无 fund_type
        refresh_market_universe(db_session, df, mgr_by_code={})

        f = db_session.get(Fund, "000001")
        assert f.fund_type == ""           # 默认空
        assert f.market_subtype == "股票型"


class TestRefreshMarketUniverse:
    def test_insert_new_codes(self, db_session):
        df = _df([
            ("000001", "华夏成长", "股票型", "stock"),
            ("000002", "招商白酒", "指数型-其他", "stock"),
            ("000003", "易方达债", "债券型-中短债", "bond"),
        ])
        result = refresh_market_universe(db_session, df, task_id=None)
        assert result["total"] == 3
        assert result["inserted"] == 3
        assert result["updated"] == 0
        assert result["failed"] == 0

        funds = {f.code: f for f in db_session.query(Fund).all()}
        assert funds["000001"].market_subtype == "股票型"
        assert funds["000001"].market_type == "stock"
        assert funds["000001"].fund_type == ""        # 新增：留空
        assert funds["000001"].is_active is True
        assert funds["000001"].name == "华夏成长"
        # 债基也正确归类
        assert funds["000003"].market_type == "bond"

    def test_update_existing_preserves_fund_type_and_is_active(self, db_session):
        """回归测试：refresh 不能污染 fund_type（雪球细分类）和 is_active"""
        # 预设：000001 是老 tab 拉过的基金，fund_type 是雪球细分类
        db_session.add(Fund(
            code="000001", name="旧名", fund_type="中长期纯债",
            age_years=5.0, size_yi=10.0, is_active=True,
        ))
        db_session.commit()

        df = _df([("000001", "新名", "债券型-长期纯债", "bond")])
        result = refresh_market_universe(db_session, df, task_id=None)

        assert result["updated"] == 1
        assert result["inserted"] == 0

        f = db_session.get(Fund, "000001")
        assert f.name == "新名"                    # 覆盖
        assert f.market_subtype == "债券型-长期纯债"  # 新增
        assert f.market_type == "bond"             # 新增
        assert f.fund_type == "中长期纯债"          # 关键：保留
        assert f.is_active is True                 # 保留
        assert f.age_years == 5.0                  # 保留
        assert f.size_yi == 10.0                   # 保留

    def test_update_existing_does_not_flip_inactive_to_active(self, db_session):
        """is_active=False 的老基金不应被 market refresh 自动激活"""
        db_session.add(Fund(code="000001", name="清盘", fund_type="债券型-长期纯债", is_active=False))
        db_session.commit()

        df = _df([("000001", "清盘改名", "债券型-长期纯债", "bond")])
        refresh_market_universe(db_session, df, task_id=None)

        f = db_session.get(Fund, "000001")
        assert f.is_active is False  # 保留 False

    def test_mixed_insert_and_update(self, db_session):
        db_session.add(Fund(code="000001", name="老基金", fund_type="中长期纯债", is_active=True))
        db_session.commit()

        df = _df([
            ("000001", "老基金改名", "债券型-长期纯债", "bond"),
            ("000002", "新基金", "股票型", "stock"),
        ])
        result = refresh_market_universe(db_session, df, task_id=None)
        assert result["inserted"] == 1
        assert result["updated"] == 1

    def test_empty_dataframe(self, db_session):
        result = refresh_market_universe(db_session, _df([]))
        assert result["total"] == 0
        assert result["inserted"] == 0

    def test_refresh_run_progress_recorded(self, db_session):
        run = RefreshRun(task_id="test-task-001", status="running", total=0)
        db_session.add(run)
        db_session.commit()

        df = _df([
            ("000001", "X", "债券型-中短债", "bond"),
            ("000002", "Y", "债券型-中短债", "bond"),
        ])
        result = refresh_market_universe(db_session, df, task_id="test-task-001")

        assert result["task_id"] == "test-task-001"
        run = db_session.get(RefreshRun, "test-task-001")
        assert run is not None
        assert run.total == 2
        assert run.completed == 2
        assert run.status == "done"
        assert run.finished_at is not None

    def test_refresh_run_error_status_on_failure(self, db_session):
        run = RefreshRun(task_id="test-task-002", status="running", total=0)
        db_session.add(run)
        db_session.commit()

        original_add = db_session.add

        def boom_add(obj):
            if isinstance(obj, Fund):
                raise RuntimeError("simulated insert failure")
            return original_add(obj)

        df = _df([("000001", "X", "债券型-中短债", "bond")])
        with patch.object(db_session, "add", side_effect=boom_add):
            result = refresh_market_universe(db_session, df, task_id="test-task-002")

        assert result["failed"] >= 1
        run = db_session.get(RefreshRun, "test-task-002")
        assert run.status == "error"
        assert run.failed >= 1

    def test_batch_commits(self, db_session):
        """batch_size=2 时 5 行应有 3 批 commit；验证数据完整写入即可"""
        rows = [(f"{i:06d}", f"基金{i}", "债券型-中短债", "bond") for i in range(5)]
        result = refresh_market_universe(db_session, _df(rows), batch_size=2)
        assert result["inserted"] == 5
        assert db_session.query(Fund).count() == 5
