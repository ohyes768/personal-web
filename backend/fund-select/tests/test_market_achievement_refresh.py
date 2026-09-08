"""
market_achievement_refresh 单测（in-memory SQLite）
"""
from datetime import date
import pandas as pd

from src.db.models import FundAchievementRank, RefreshRun
from src.services.market_achievement_refresh import refresh as refresh_market_achievement


def _mock_ach_df(code: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"业绩类型": "年度业绩", "周期": "1y",
         "本产品区间收益": 15.5, "本产品最大回撒": -3.2,
         "周期收益同类排名": "100/500"},
        {"业绩类型": "阶段业绩", "周期": "3y",
         "本产品区间收益": 50.0, "本产品最大回撒": -8.0,
         "周期收益同类排名": "120/600"},
    ])


class TestRefreshMarketAchievement:
    def test_insert_new_codes(self, db_session):
        ach_data = {
            "000001": _mock_ach_df("000001"),
            "000002": _mock_ach_df("000002"),
        }
        result = refresh_market_achievement(db_session, ach_data)
        assert result["total"] == 2
        assert result["inserted"] == 2

        ranks = {(r.code, r.period_kind, r.period): r.peer_rank
                 for r in db_session.query(FundAchievementRank).all()}
        assert ranks[("000001", "年度业绩", "1y")] == "100/500"
        assert ranks[("000001", "阶段业绩", "3y")] == "120/600"

    def test_overwrite_existing(self, db_session):
        """同 code 多次 refresh：先 delete 旧行再 insert"""
        ach_data_v1 = {"000001": _mock_ach_df("000001")}
        refresh_market_achievement(db_session, ach_data_v1)

        # 第二次用不同数据
        ach_data_v2 = {
            "000001": pd.DataFrame([
                {"业绩类型": "年度业绩", "周期": "1y",
                 "本产品区间收益": 99.0, "本产品最大回撒": -1.0,
                 "周期收益同类排名": "5/500"},
            ])
        }
        refresh_market_achievement(db_session, ach_data_v2)

        # 只剩 1 条（1y），不是 3 条
        all_rows = db_session.query(FundAchievementRank).filter_by(code="000001").all()
        assert len(all_rows) == 1
        assert all_rows[0].peer_rank == "5/500"

    def test_refresh_run_progress(self, db_session):
        run = RefreshRun(task_id="test-ach", status="running", total=0)
        db_session.add(run)
        db_session.commit()

        ach_data = {"000001": _mock_ach_df("000001")}
        refresh_market_achievement(db_session, ach_data, task_id="test-ach")

        run = db_session.get(RefreshRun, "test-ach")
        assert run.status == "done"
        assert run.total == 1
        assert run.completed == 1
        assert run.finished_at is not None

    def test_empty_data(self, db_session):
        result = refresh_market_achievement(db_session, {})
        assert result["total"] == 0
        assert result["inserted"] == 0
