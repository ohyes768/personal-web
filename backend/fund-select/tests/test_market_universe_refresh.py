"""
全市场基金名单 refresh 单测（in-memory SQLite + conftest 的 db_session）

关键回归点：
- 已存在基金：仅更新 name / market_type / updated_at，保留 fund_type / is_active
- 新增基金：fund_type 留空、is_active=True
- 进度写入 RefreshRun
"""
from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from src.db.models import Fund, RefreshRun
from src.services.market_universe_refresh import refresh as refresh_market_universe


def _df(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["code", "name", "market_type"])


class TestRefreshMarketUniverse:
    def test_insert_new_codes(self, db_session):
        df = _df([
            ("000001", "华夏成长", "混合型"),
            ("000002", "招商白酒", "指数型"),
            ("000003", "易方达债", "债券型"),
        ])
        result = refresh_market_universe(db_session, df, task_id=None)
        assert result["total"] == 3
        assert result["inserted"] == 3
        assert result["updated"] == 0
        assert result["failed"] == 0

        funds = {f.code: f for f in db_session.query(Fund).all()}
        assert funds["000001"].market_type == "混合型"
        assert funds["000001"].fund_type == ""        # 新增：留空
        assert funds["000001"].is_active is True
        assert funds["000001"].name == "华夏成长"

    def test_update_existing_preserves_fund_type_and_is_active(self, db_session):
        """回归测试：refresh 不能污染 fund_type（雪球细分类）"""
        # 预设：000001 是老 tab 拉过的基金，fund_type 是雪球细分类
        db_session.add(Fund(
            code="000001", name="旧名", fund_type="中长期纯债",
            age_years=5.0, size_yi=10.0, is_active=True,
        ))
        db_session.commit()

        df = _df([("000001", "新名", "债券型")])
        result = refresh_market_universe(db_session, df, task_id=None)

        assert result["updated"] == 1
        assert result["inserted"] == 0

        f = db_session.get(Fund, "000001")
        assert f.name == "新名"              # 覆盖
        assert f.market_type == "债券型"      # 新增
        assert f.fund_type == "中长期纯债"    # 关键：保留
        assert f.is_active is True            # 保留
        assert f.age_years == 5.0             # 保留
        assert f.size_yi == 10.0              # 保留

    def test_update_existing_does_not_flip_inactive_to_active(self, db_session):
        """is_active=False 的老基金不应被 market refresh 自动激活"""
        db_session.add(Fund(code="000001", name="清盘", fund_type="债券型", is_active=False))
        db_session.commit()

        df = _df([("000001", "清盘改名", "债券型")])
        refresh_market_universe(db_session, df, task_id=None)

        f = db_session.get(Fund, "000001")
        assert f.is_active is False  # 保留 False

    def test_mixed_insert_and_update(self, db_session):
        db_session.add(Fund(code="000001", name="老基金", fund_type="中长期纯债", is_active=True))
        db_session.commit()

        df = _df([
            ("000001", "老基金改名", "债券型"),
            ("000002", "新基金", "股票型"),
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

        df = _df([("000001", "X", "债券型"), ("000002", "Y", "债券型")])
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

        # 让 session.add 在加 Fund 时抛异常（不 patch Fund 类，避免 SQLAlchemy select 也坏掉）
        from src.services import market_universe_refresh as mur

        original_add = db_session.add

        def boom_add(obj):
            if isinstance(obj, Fund):
                raise RuntimeError("simulated insert failure")
            return original_add(obj)

        df = _df([("000001", "X", "债券型")])
        with patch.object(db_session, "add", side_effect=boom_add):
            result = refresh_market_universe(db_session, df, task_id="test-task-002")

        assert result["failed"] >= 1
        run = db_session.get(RefreshRun, "test-task-002")
        assert run.status == "error"
        assert run.failed >= 1

    def test_batch_commits(self, db_session):
        """batch_size=2 时 5 行应有 3 批 commit；验证数据完整写入即可"""
        rows = [(f"{i:06d}", f"基金{i}", "债券型") for i in range(5)]
        result = refresh_market_universe(db_session, _df(rows), batch_size=2)
        assert result["inserted"] == 5
        assert db_session.query(Fund).count() == 5
