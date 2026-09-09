"""
market_size_refresh 单测（in-memory SQLite + conftest 的 db_session）

关键回归点：
- size_yi / age_years / established_date：已有非空值**不被覆盖**（保护 L2 已写入数据）
- 空字段被填充
- mgr_company：始终用 msm 接口的（覆盖 L0 阶段）
- 进度写入 RefreshRun
- Fund 不存在 → skipped
"""
from datetime import UTC, datetime, date
from unittest.mock import patch

import pytest

from src.db.models import Fund, RefreshRun
from src.services.market_size_refresh import refresh as refresh_market_size


def _row(code: str, **kw) -> dict:
    """构造 fetcher 返回的 row 字典：code / established_date / age_years / size_yi / mgr_company"""
    defaults = {
        "code": code,
        "established_date": date(2020, 1, 1),
        "age_years": 5.0,
        "size_yi": 10.0,
        "mgr_company": "新公司",
    }
    defaults.update(kw)
    return defaults


class TestRefreshMarketSize:
    def test_insert_fields_into_existing_fund(self, db_session):
        """已有 Fund（所有 size/age 字段为 None）→ 全部字段被写入。"""
        db_session.add(Fund(code="000001", name="测试基金", is_active=True))
        db_session.commit()

        result = refresh_market_size(db_session, [_row("000001")])

        assert result["updated"] == 1
        assert result["skipped"] == 0
        f = db_session.get(Fund, "000001")
        assert f.size_yi == 10.0
        assert f.age_years == 5.0
        assert f.established_date == date(2020, 1, 1)
        assert f.mgr_company == "新公司"

    def test_does_not_overwrite_existing_size_yi(self, db_session):
        """关键不变量：已有 size_yi 不被覆盖（保护 L2 已写入数据）"""
        db_session.add(Fund(
            code="000001", name="测试基金", is_active=True,
            size_yi=99.0, age_years=8.0, established_date=date(2018, 1, 1),
        ))
        db_session.commit()

        refresh_market_size(db_session, [_row("000001", size_yi=1.0, age_years=1.0,
                                                established_date=date(2025, 1, 1))])

        f = db_session.get(Fund, "000001")
        assert f.size_yi == 99.0          # 保留
        assert f.age_years == 8.0         # 保留
        assert f.established_date == date(2018, 1, 1)  # 保留

    def test_fills_only_empty_fields(self, db_session):
        """部分字段已有，部分空 → 只填空的"""
        db_session.add(Fund(
            code="000001", name="测试基金", is_active=True,
            size_yi=99.0,             # 已有，不覆盖
            age_years=None,           # 空，会被填
            established_date=None,    # 空，会被填
        ))
        db_session.commit()

        refresh_market_size(db_session, [_row(
            "000001", size_yi=1.0, age_years=5.0, established_date=date(2020, 1, 1),
        )])

        f = db_session.get(Fund, "000001")
        assert f.size_yi == 99.0
        assert f.age_years == 5.0
        assert f.established_date == date(2020, 1, 1)

    def test_mgr_company_always_overwritten(self, db_session):
        """mgr_company：msm 接口始终更准，覆盖 L0 阶段写入的值"""
        db_session.add(Fund(
            code="000001", name="测试基金", is_active=True,
            mgr_company="L0 老公司",
        ))
        db_session.commit()

        refresh_market_size(db_session, [_row("000001", mgr_company="msm 新公司")])

        f = db_session.get(Fund, "000001")
        assert f.mgr_company == "msm 新公司"  # 覆盖

    def test_mgr_company_empty_does_not_clear_existing(self, db_session):
        """msm 接口 mgr_company 为空 → 不覆盖（保持已有值）"""
        db_session.add(Fund(
            code="000001", name="测试基金", is_active=True,
            mgr_company="L0 老公司",
        ))
        db_session.commit()

        refresh_market_size(db_session, [_row("000001", mgr_company=None)])

        f = db_session.get(Fund, "000001")
        assert f.mgr_company == "L0 老公司"  # 保留

    def test_skips_nonexistent_fund(self, db_session):
        """Fund 不存在 → skipped=1，updated=0"""
        result = refresh_market_size(db_session, [_row("999999")])

        assert result["skipped"] == 1
        assert result["updated"] == 0
        # 不创建 Fund
        assert db_session.get(Fund, "999999") is None

    def test_does_not_create_fund_if_missing(self, db_session):
        """不存在的 code 不会自动新增（refresh 仅 upsert 已有基金）"""
        result = refresh_market_size(db_session, [_row("000001")])

        assert result["skipped"] == 1
        assert db_session.query(Fund).count() == 0

    def test_skips_rows_with_empty_code(self, db_session):
        """row.code 为空 → failed+=1"""
        result = refresh_market_size(db_session, [{"code": "", "size_yi": 10.0}])

        assert result["failed"] == 1
        assert result["updated"] == 0

    def test_empty_rows(self, db_session):
        """空 rows 列表 → 返回 0/0/0/0"""
        result = refresh_market_size(db_session, [])

        assert result["total"] == 0
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["failed"] == 0

    def test_refresh_run_progress_recorded(self, db_session):
        """task_id 非空时同步写 RefreshRun"""
        run = RefreshRun(task_id="test-task-001", status="running", total=0)
        db_session.add(run)
        db_session.commit()

        db_session.add(Fund(code="000001", name="A", is_active=True))
        db_session.commit()

        result = refresh_market_size(
            db_session, [_row("000001")], task_id="test-task-001",
        )

        assert result["task_id"] == "test-task-001"
        run = db_session.get(RefreshRun, "test-task-001")
        assert run.total == 1
        assert run.completed == 1
        assert run.status == "done"
        assert run.finished_at is not None

    def test_refresh_run_error_status_on_failure(self, db_session):
        """处理异常 → run.status='error'，run.failed > 0"""
        run = RefreshRun(task_id="test-task-002", status="running", total=0)
        db_session.add(run)
        db_session.commit()

        db_session.add(Fund(code="000001", name="A", is_active=True))
        db_session.commit()

        original_get = db_session.get

        def boom_get(model, pk):
            if model is Fund and pk == "000001":
                raise RuntimeError("simulated failure")
            return original_get(model, pk)

        with patch.object(db_session, "get", side_effect=boom_get):
            result = refresh_market_size(
                db_session, [_row("000001")], task_id="test-task-002",
            )

        assert result["failed"] >= 1
        run = db_session.get(RefreshRun, "test-task-002")
        assert run.status == "error"

    def test_batch_commits(self, db_session):
        """batch_size=2 时 5 行应有 3 批 commit；验证数据完整写入"""
        for i in range(5):
            db_session.add(Fund(code=f"{i:06d}", name=f"基金{i}", is_active=True))
        db_session.commit()

        rows = [_row(f"{i:06d}") for i in range(5)]
        result = refresh_market_size(db_session, rows, batch_size=2)

        assert result["updated"] == 5
        # 所有 5 只基金 size_yi 都已写入
        for i in range(5):
            f = db_session.get(Fund, f"{i:06d}")
            assert f.size_yi == 10.0

    def test_does_not_touch_other_fund_fields(self, db_session):
        """关键回归：不污染 fund_type / market_subtype / market_type / mgr_name / mgr_days 等"""
        db_session.add(Fund(
            code="000001", name="测试基金", is_active=True,
            fund_type="中长期纯债",
            market_subtype="债券型-长期纯债",
            market_type="bond",
            mgr_name="老经理",
            mgr_days=5000,
            mgr_experience_years=13.68,
        ))
        db_session.commit()

        refresh_market_size(db_session, [_row("000001", mgr_company="新公司")])

        f = db_session.get(Fund, "000001")
        assert f.fund_type == "中长期纯债"      # 不动
        assert f.market_subtype == "债券型-长期纯债"
        assert f.market_type == "bond"
        assert f.mgr_name == "老经理"
        assert f.mgr_days == 5000
        assert f.mgr_experience_years == 13.68
        assert f.mgr_company == "新公司"        # 覆盖

    def test_partial_row_data(self, db_session):
        """row 只有部分字段（其他为 None）→ 不写入 None 字段（保护已有值）"""
        db_session.add(Fund(
            code="000001", name="测试基金", is_active=True,
            size_yi=5.0,  # 已有 size_yi
        ))
        db_session.commit()

        # fetcher 漏掉 size_yi 字段（age_years/established_date/mgr_company 也都没有）
        refresh_market_size(db_session, [{
            "code": "000001",
            "size_yi": None,
            "age_years": None,
            "established_date": None,
            "mgr_company": None,
        }])

        f = db_session.get(Fund, "000001")
        assert f.size_yi == 5.0  # 保留
        assert f.age_years is None
        assert f.established_date is None
        assert f.mgr_company is None  # None 不会覆盖已有（这里本来也是 None）

    def test_updated_at_changed(self, db_session):
        """字段实际变化时 updated_at 更新"""
        original_dt = datetime(2020, 1, 1)  # 去掉 tzinfo：SQLite 不保留 tz
        db_session.add(Fund(code="000001", name="A", is_active=True,
                            size_yi=None, age_years=None, established_date=None,
                            updated_at=original_dt))
        db_session.commit()

        refresh_market_size(db_session, [_row("000001")])

        f = db_session.get(Fund, "000001")
        # updated_at 应被刷新到 now（> 原值）
        assert f.updated_at > original_dt
