"""v3 回溯脚本测试（11-14-sharpe-board-v3-yearly-peer，AC5/AC7）

全程 mock 网络：净值/基准/TRI 都用合成数据，验证落库行为而非算力。

关注点：
- 幂等：重复跑不重复写（complete 周跳过）
- v2 数据零影响（版本隔离）
- 周键全部落在周一
- dry-run 不写库
- 年度 peer 数据全周共享且正确进入 evidence
"""
import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from src.db.models import (
    Fund, FundAchievementRank, FundBenchmark, FundPerformance, SharpeBoardObservation,
    SharpeBoardWeek,
)

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_v3_yearly_peer.py"
_spec = importlib.util.spec_from_file_location("backfill_v3", _SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)


def _nav_df(n: int = 1200, end="2026-11-01", seed: int = 1) -> pd.DataFrame:
    """合成净值：日增长率 %，足够 3 年样本。"""
    rng = np.random.default_rng(seed)
    g = rng.normal(0.0004, 0.0009, n)
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    return pd.DataFrame({"净值日期": dates, "日增长率": g * 100.0})


@pytest.fixture
def seeded(db_session, monkeypatch, tmp_path):
    """小 universe：2 只基金，都有 3 年年度排名（达标）+ 净值。"""
    for code in ("700001", "700002"):
        db_session.add(Fund(
            code=code, name=f"基金{code}", fund_type="股票型",
            age_years=6.0, size_yi=20.0, mgr_name="张", mgr_company="某司",
            mgr_days=3000, mgr_experience_years=8.0,
            mgr_experience_years_max=8.0, is_active=True,
            market_subtype="混合型-偏股"))
        db_session.add(FundPerformance(
            code=code, as_of_date=date(2026, 9, 1), dd_3y=-10.0, ret_3y=50.0))
        # 年度排名：两年达标（前 10%）
        for year in ("2023", "2024", "2025"):
            db_session.add(FundAchievementRank(
                code=code, period_kind="年度业绩", period=year,
                ret=10.0, max_dd=-5.0, peer_rank="1/10",
                as_of_date=date(2026, 9, 9)))
        # TRI 存在 → 走有基准路径
        db_session.add(FundBenchmark(
            code=code, date=date(2026, 9, 1), tri=100.0, source="test"))
    db_session.commit()

    # load_fund_codes 返回这 2 只（stock 来源）
    monkeypatch.setattr(bf, "load_fund_codes", lambda *a, **kw: ["700001", "700002"])
    # 净值 / 基准全部用合成数据，不走网络
    monkeypatch.setattr(bf, "load_nav_histories",
                        lambda codes, cache: {c: _nav_df(seed=i) for i, c in enumerate(codes)})
    monkeypatch.setattr(bf, "load_bench_returns",
                        lambda codes, start, cache: {c: pd.Series(
                            np.random.default_rng(9).normal(0.0002, 0.0005, 1200),
                            index=pd.bdate_range(end="2026-11-01", periods=1200))
                            for c in codes})
    monkeypatch.setattr(bf, "tri_codes", lambda db: {"700001", "700002"})
    return db_session


def _run(seeded, monkeypatch, *, publish: bool, weeks=("2026-09-07", "2026-09-14")):
    """跑脚本 main()（patch argv 与 SessionLocal）。"""
    argv = ["prog", "--start-week", weeks[0], "--end-week", weeks[-1], "--ref-year", "2026"]
    if publish:
        argv.append("--publish")
    monkeypatch.setattr("sys.argv", argv)
    monkeypatch.setattr(bf, "SessionLocal", lambda: seeded)
    # publish 内部会 commit；用同一个 session 便于断言
    return bf.main()


class TestBackfillV3:
    def test_dry_run_writes_nothing(self, seeded, monkeypatch):
        before_w = seeded.query(SharpeBoardWeek).count()
        before_o = seeded.query(SharpeBoardObservation).count()
        assert _run(seeded, monkeypatch, publish=False) == 0
        assert seeded.query(SharpeBoardWeek).count() == before_w
        assert seeded.query(SharpeBoardObservation).count() == before_o

    def test_publish_creates_v3_weeks_on_mondays(self, seeded, monkeypatch):
        _run(seeded, monkeypatch, publish=True)
        rows = seeded.execute(
            select(SharpeBoardWeek).where(SharpeBoardWeek.profile_version == "v3")
        ).scalars().all()
        assert len(rows) == 4, f"2 sources × 2 weeks = 4，实际 {len(rows)}"
        for r in rows:
            assert r.week_start.weekday() == 0, f"{r.week_start} 不是周一"
            assert r.trigger == "backfill"
            assert r.profile_version == "v3"

    def test_evidence_contains_yearly_peer(self, seeded, monkeypatch):
        _run(seeded, monkeypatch, publish=True)
        obs = seeded.query(SharpeBoardObservation).first()
        assert obs is not None
        import json
        ev = json.loads(obs.evidence_json)
        assert ev["peer"]["qualified_years"] == 3
        assert ev["peer"]["window"] == ["2023", "2024", "2025"]

    def test_idempotent_second_run_skips(self, seeded, monkeypatch):
        _run(seeded, monkeypatch, publish=True)
        after_first = seeded.query(SharpeBoardWeek).count()
        obs_first = seeded.query(SharpeBoardObservation).count()
        _run(seeded, monkeypatch, publish=True)
        assert seeded.query(SharpeBoardWeek).count() == after_first
        assert seeded.query(SharpeBoardObservation).count() == obs_first

    def test_v2_data_untouched(self, seeded, monkeypatch):
        """AC7：v2 已有的周与观测不受回溯影响。"""
        seeded.add(SharpeBoardWeek(
            source="stock", profile_version="v2", week_start=date(2026, 11, 9),
            profile_json="{}", profile_hash="h", algorithm_version="risk-3y-v2",
            status="complete", selected_count=1,
            started_at=datetime(2026, 11, 13, 0, 5)))
        seeded.flush()
        w2 = seeded.query(SharpeBoardWeek).filter_by(profile_version="v2").one()
        seeded.add(SharpeBoardObservation(
            week_id=w2.id, code="700001", name="基金700001", sharpe=1.2))
        seeded.commit()
        v2_obs_before = seeded.query(SharpeBoardObservation).filter(
            SharpeBoardObservation.week_id == w2.id).count()

        _run(seeded, monkeypatch, publish=True)

        v2_rows = seeded.query(SharpeBoardWeek).filter_by(profile_version="v2").all()
        assert len(v2_rows) == 1
        assert v2_rows[0].selected_count == 1      # 未被改写
        assert seeded.query(SharpeBoardObservation).filter(
            SharpeBoardObservation.week_id == w2.id).count() == v2_obs_before

    def test_yearly_window_respected(self, seeded, monkeypatch):
        """ref-year=2027 → 窗口 2024/2025/2026，2026 无数据 → 只有 2 年达标。"""
        argv = ["prog", "--start-week", "2026-09-07", "--end-week", "2026-09-07",
                "--ref-year", "2027", "--publish"]
        monkeypatch.setattr("sys.argv", argv)
        monkeypatch.setattr(bf, "SessionLocal", lambda: seeded)
        bf.main()
        obs = seeded.query(SharpeBoardObservation).first()
        import json
        ev = json.loads(obs.evidence_json)
        assert ev["peer"]["window"] == ["2024", "2025", "2026"]
        assert ev["peer"]["qualified_years"] == 2
        assert ev["peer"]["years"]["2026"] is None
