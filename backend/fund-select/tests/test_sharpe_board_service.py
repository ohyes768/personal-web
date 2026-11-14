"""
夏普榜单步骤 1 测试：唯一约束 / 重启保留 / 规则 profile / 周键 / 冻结语义

对应 implement.md 步骤 1（AC5、AC7、AC8）：
- 同 source/version/week 两行失败，不同 source/version 可共存
- tmp_path 文件 SQLite：重新开连接数据仍在
- recording_week 跨年/跨周/时区/naive 拒绝
- complete 零入选、failed、skipped_no_new_data 三种状态区分；complete 同周重试不覆盖
"""
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.data.market_subtype_map import DISCOVERY_STOCK_SUBTYPES
from src.db.models import Base, FundPerformance, SharpeBoardObservation, SharpeBoardWeek
from src.services import sharpe_board_service as sbs
from src.services.sharpe_capture import SharpeRunCapture, freeze_dd_rows


def _make_session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return Session()


def _memory_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _mk_week(source="stock", version="v1", week=date(2026, 11, 2), status="complete", **kw):
    """周批次行工厂：默认值可被 kw 覆盖"""
    defaults = dict(
        profile_json="{}",
        profile_hash="h0",
        algorithm_version="risk-3y-v1",
        status=status,
        selected_count=0,
        started_at=datetime(2026, 11, 7, 8, 5),
    )
    defaults.update(kw)
    return SharpeBoardWeek(source=source, profile_version=version, week_start=week, **defaults)


class TestUniqueConstraint:
    def test_same_source_version_week_rejected(self, db_session):
        """同 source/version/week 联合唯一：第二行 commit 必须 IntegrityError"""
        db_session.add_all([
            _mk_week(status="complete"),
            _mk_week(status="failed", errors_json='["x"]'),
        ])
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_different_source_coexist(self, db_session):
        """同周同版本、不同来源可共存（来源隔离，不混算）"""
        db_session.add_all([
            _mk_week(source="stock"),
            _mk_week(source="discovery-stock"),
        ])
        db_session.commit()
        assert db_session.query(SharpeBoardWeek).count() == 2

    def test_different_version_coexist(self, db_session):
        """同周同来源、不同规则版本可共存（版本隔离，不混算）"""
        db_session.add_all([
            _mk_week(version="v1"),
            _mk_week(version="v2"),
        ])
        db_session.commit()
        assert db_session.query(SharpeBoardWeek).count() == 2

    def test_observation_same_week_code_rejected(self, db_session):
        """观测表 week_id+code 联合唯一：一只基金同周只计一次"""
        week = _mk_week()
        db_session.add(week)
        db_session.commit()
        db_session.add_all([
            SharpeBoardObservation(week_id=week.id, code="000001", name="A", sharpe=0.9),
            SharpeBoardObservation(week_id=week.id, code="000001", name="A重复", sharpe=0.9),
        ])
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestPersistence:
    def test_survives_reconnect(self, tmp_path):
        """文件 SQLite：dispose 后重新开连接数据仍在（重启保留）"""
        db_path = tmp_path / "board.db"
        url = f"sqlite:///{db_path.as_posix()}"
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        s1 = _make_session(engine)
        sbs.record_week_attempt(
            s1, source="stock", profile_version="v1", week_start=date(2026, 11, 2),
            status="complete", started_at=datetime(2026, 11, 7, 8, 5, tzinfo=UTC),
            selected_count=3,
        )
        s1.close()
        engine.dispose()

        engine2 = create_engine(url)
        Base.metadata.create_all(engine2)  # 幂等，不应改动已有数据
        s2 = _make_session(engine2)
        row = sbs.get_board_week(s2, "stock", "v1", date(2026, 11, 2))
        assert row is not None
        assert row.status == "complete"
        assert row.selected_count == 3
        assert row.profile_hash == sbs.canonical_hash(sbs.get_profile("stock", "v1"))
        s2.close()
        engine2.dispose()


class TestProfiles:
    def test_two_stock_profiles_exist(self):
        assert sbs.get_profile("stock", "v1")["source"] == "stock"
        assert sbs.get_profile("discovery-stock", "v1")["source"] == "discovery-stock"

    def test_unknown_profile_rejected(self):
        """债基首版不接夏普（PRD），无 profile 即不可用"""
        with pytest.raises(KeyError):
            sbs.get_profile("bond", "v1")

    def test_entry_filters_are_stock_defaults(self):
        """入选条件 = PRD 首版工程默认值（股基 tab 当前默认筛选），两来源一致"""
        expected = {
            "min_age": 3,        # 成立 ≥3 年
            "min_size_yi": 5,    # 规模 ≥5 亿
            "max_dd_3y": 30,     # 近三年回撤绝对值 ≤30%（库内负值按绝对值比较）
            "min_mgr_exp": 5,    # 经理从业 ≥5 年
            "min_sharpe": 0.8,   # 近三年夏普 ≥0.8（含等于）
            "exclude_qdii": False,
        }
        assert sbs.get_profile("stock", "v1")["filters"] == expected
        assert sbs.get_profile("discovery-stock", "v1")["filters"] == expected

    def test_market_prefilters_frozen(self):
        """市场来源受现有采集预筛约束（weekly_refresh 现值）；雪球三分法无收益预筛"""
        assert sbs.get_profile("discovery-stock", "v1")["collection_prefilters"] == {
            "min_ret_3y": 20, "min_size_yi": 5, "min_mgr_exp": 5,
        }
        assert sbs.get_profile("stock", "v1")["collection_prefilters"] == {}

    def test_discovery_subtypes_frozen_copy(self):
        """市场来源使用 DISCOVERY_STOCK_SUBTYPES 确定副本；返回值是拷贝不污染常量"""
        prof = sbs.get_profile("discovery-stock", "v1")
        assert prof["market_subtypes"] == list(DISCOVERY_STOCK_SUBTYPES)
        assert len(prof["market_subtypes"]) == len(set(prof["market_subtypes"]))
        prof["market_subtypes"].append("污染")
        assert sbs.get_profile("discovery-stock", "v1")["market_subtypes"] == list(DISCOVERY_STOCK_SUBTYPES)

    def test_stock_source_has_no_subtype_scope(self):
        """雪球三分法走 yaml 名单，不按 subtype 圈定"""
        assert sbs.get_profile("stock", "v1")["market_subtypes"] is None

    def test_algorithm_version_declared(self):
        assert sbs.get_profile("stock", "v1")["algorithm_version"]
        assert (sbs.get_profile("stock", "v1")["algorithm_version"]
                == sbs.get_profile("discovery-stock", "v1")["algorithm_version"])


class TestCanonicalJson:
    def test_hash_independent_of_key_order(self):
        a = {"filters": {"min_age": 3, "min_sharpe": 0.8}, "source": "stock"}
        b = {"source": "stock", "filters": {"min_sharpe": 0.8, "min_age": 3}}
        assert sbs.canonical_hash(a) == sbs.canonical_hash(b)

    def test_json_compact_sorted_chinese_raw(self):
        text = sbs.canonical_json({"b": 2, "a": "中文"})
        assert " " not in text                      # 紧凑分隔符
        assert text.index('"a"') < text.index('"b"')  # 键排序
        assert "中文" in text and "\\u" not in text    # 中文不转义

    def test_profile_hash_distinguishes_sources(self):
        assert (sbs.canonical_hash(sbs.get_profile("stock", "v1"))
                != sbs.canonical_hash(sbs.get_profile("discovery-stock", "v1")))


class TestRecordingWeek:
    def test_cross_year(self):
        """跨年：2027-01-01（周五，北京时间）归 2026-12-28 当周"""
        started = datetime.fromisoformat("2027-01-01T10:05:00+08:00")
        assert sbs.recording_week(started).isoformat() == "2026-12-28"

    def test_midweek_maps_to_monday(self):
        # 2026-11-04 是周三
        started = datetime.fromisoformat("2026-11-04T10:05:00+08:00")
        assert sbs.recording_week(started) == date(2026, 11, 2)

    def test_sunday_belongs_to_same_iso_week(self):
        # 2026-11-01 是周日 → 本 ISO 周一 2026-10-26
        started = datetime.fromisoformat("2026-11-01T23:00:00+08:00")
        assert sbs.recording_week(started) == date(2026, 10, 26)

    def test_utc_input_converted_to_shanghai(self):
        # 2026-11-07 17:00 UTC = 北京 2026-11-08 01:00（周日）→ 2026-11-02 当周
        started = datetime(2026, 11, 7, 17, 0, tzinfo=UTC)
        assert sbs.recording_week(started) == date(2026, 11, 2)

    def test_naive_datetime_rejected(self):
        """不接收 naive datetime（R7 日期真实性）"""
        with pytest.raises(ValueError):
            sbs.recording_week(datetime(2026, 11, 4, 10, 5))


class TestWeekStatusLifecycle:
    def _attempt(self, db, **kw):
        defaults = dict(
            source="stock", profile_version="v1", week_start=date(2026, 11, 2),
            status="complete", started_at=datetime(2026, 11, 7, 8, 5, tzinfo=UTC),
        )
        defaults.update(kw)
        return sbs.record_week_attempt(db, **defaults)

    def test_complete_empty_board_is_valid(self, db_session):
        """成功零入选是有效空榜（R6）：complete + selected_count=0 + published_at"""
        row, written = self._attempt(db_session, selected_count=0)
        assert written is True
        assert row.status == "complete"
        assert row.selected_count == 0
        assert row.published_at is not None

    def test_failed_keeps_errors_and_no_publish(self, db_session):
        row, _ = self._attempt(db_session, status="failed",
                               errors=["000001 fetch benchmark failed"])
        assert row.status == "failed"
        assert row.published_at is None
        assert json.loads(row.errors_json) == ["000001 fetch benchmark failed"]

    def test_skipped_no_new_data_keeps_diagnostics(self, db_session):
        row, _ = self._attempt(db_session, status="skipped_no_new_data",
                               diagnostics={"stale_codes": 5})
        assert row.status == "skipped_no_new_data"
        assert row.published_at is None
        assert json.loads(row.diagnostics_json) == {"stale_codes": 5}

    def test_unknown_status_rejected(self, db_session):
        """running 是 scheduler 内存态，不落周表（design）"""
        with pytest.raises(ValueError):
            self._attempt(db_session, status="running")

    def test_naive_started_at_rejected(self, db_session):
        with pytest.raises(ValueError):
            self._attempt(db_session, started_at=datetime(2026, 11, 7, 8, 5))

    def test_complete_not_overwritten_by_retry(self, db_session):
        """首次 complete 冻结：同周重试不覆盖（AC8）"""
        row, _ = self._attempt(db_session, selected_count=7)
        frozen = (row.status, row.selected_count, row.published_at, row.profile_hash)
        again, written = self._attempt(db_session, status="failed", errors=["retry"])
        assert written is False
        assert again.id == row.id
        reread = sbs.get_board_week(db_session, "stock", "v1", date(2026, 11, 2))
        assert (reread.status, reread.selected_count,
                reread.published_at, reread.profile_hash) == frozen

    def test_failed_then_complete_same_week(self, db_session):
        """failed/skipped 可同周重试：失败 → 成功覆盖（AC6）"""
        self._attempt(db_session, status="failed", errors=["net down"])
        row, written = self._attempt(db_session, selected_count=4)
        assert written is True
        assert row.status == "complete"
        reread = sbs.get_board_week(db_session, "stock", "v1", date(2026, 11, 2))
        assert reread.status == "complete"
        assert reread.errors_json is None      # 重试成功后错误清空
        assert reread.published_at is not None

    def test_skipped_then_complete_same_week(self, db_session):
        self._attempt(db_session, status="skipped_no_new_data", diagnostics={"stale": 300})
        row, written = self._attempt(db_session, selected_count=2)
        assert written is True
        assert row.status == "complete"

    def test_profile_snapshot_saved_with_board(self, db_session):
        """完整规则副本随榜保存（R8：规则变更换版本，数据记录完整规则）"""
        row, _ = self._attempt(db_session)
        prof = sbs.get_profile("stock", "v1")
        assert row.profile_json == sbs.canonical_json(prof)
        assert row.profile_hash == sbs.canonical_hash(prof)
        assert row.algorithm_version == prof["algorithm_version"]


class TestObservation:
    def _mk_week(self, db_session, week=date(2026, 11, 2)):
        week_row = _mk_week(week=week)
        db_session.add(week_row)
        db_session.commit()
        return week_row

    def test_observation_fields_roundtrip(self, db_session):
        """观测快照字段：名称/夏普/样本尾日/样本天数/证据 可写入读回"""
        week = self._mk_week(db_session)
        db_session.add(SharpeBoardObservation(
            week_id=week.id, code="000001", name="基金A快照", sharpe=0.95,
            metric_calculated_at=datetime(2026, 11, 7, 8, 4, 30),
            returns_end_date=date(2026, 11, 6), sample_days=746,
            evidence_json='{"risk_run_id": "r1"}',
        ))
        db_session.commit()
        obs = db_session.query(SharpeBoardObservation).one()
        assert obs.name == "基金A快照"
        assert obs.sharpe == 0.95
        assert obs.returns_end_date == date(2026, 11, 6)
        assert obs.sample_days == 746
        assert json.loads(obs.evidence_json) == {"risk_run_id": "r1"}

    def test_observation_not_tied_to_funds_table(self, db_session):
        """不引用实时 Fund：funds 表无此 code 也能保留历史观测（R8：清盘不抹历史）"""
        week = self._mk_week(db_session)
        db_session.add(SharpeBoardObservation(
            week_id=week.id, code="999999", name="已清盘基金", sharpe=0.81,
        ))
        db_session.commit()
        assert db_session.query(SharpeBoardObservation).count() == 1


# ─────────────────────────────────────────────────────────────
# 步骤 3：dd_3y 冻结 + 原子发布（implement 步骤 3：AC5、AC6、AC8、AC10）
# ─────────────────────────────────────────────────────────────

class TestFreezeDdRows:
    """dd_3y 在 FundPerformance 行上，freeze_base_row 冻结不到，单独补冻结"""

    def test_merges_dd3y_into_base_rows(self, db_session):
        from src.db.models import Fund
        db_session.add(Fund(code="000001", name="A", fund_type="股票型", is_active=True))
        db_session.add(FundPerformance(code="000001", as_of_date=date(2026, 9, 1), dd_3y=-12.5))
        db_session.commit()
        base = {"000001": {"name": "A", "market_subtype": "股票型", "age_years": 6.0,
                           "size_yi": 10.0, "mgr_experience_years": 8.0}}
        freeze_dd_rows(db_session, base)
        assert base["000001"]["dd_3y"] == -12.5

    def test_missing_perf_row_gives_none(self, db_session):
        base = {"999999": {"name": "X", "market_subtype": "股票型", "age_years": 6.0,
                           "size_yi": 10.0, "mgr_experience_years": 8.0}}
        freeze_dd_rows(db_session, base)
        assert base["999999"]["dd_3y"] is None

    def test_skips_codes_not_in_base_rows(self, db_session):
        """snapshot 失败的 code 不在 base_rows：不查不写（本就不参评）"""
        from src.db.models import Fund
        db_session.add(Fund(code="000001", name="A", fund_type="股票型", is_active=True))
        db_session.add(FundPerformance(code="000001", as_of_date=date(2026, 9, 1), dd_3y=-5.0))
        db_session.commit()
        base: dict = {}
        freeze_dd_rows(db_session, base)
        assert base == {}


def _qualified_capture(run_id: str, codes: list[str], *, sharpe=1.0,
                       end=date(2026, 10, 30), universe_extra: int = 0) -> SharpeRunCapture:
    """全部入选合格的 capture 工厂（universe 重复项验证按 code 去重）"""
    base_rows = {}
    risk_rows = {}
    for code in codes:
        base_rows[code] = {
            "name": f"基金{code}", "market_subtype": "股票型", "age_years": 6.0,
            "size_yi": 20.0, "mgr_experience_years": 8.0, "dd_3y": -10.0,
        }
        risk_rows[code] = {
            "sharpe": sharpe, "sample_days": 746, "returns_end_date": end,
            "calculated_at": datetime(2026, 10, 31, 8, 40, tzinfo=UTC),
            "benchmark_source": "fetched",
        }
    universe = list(codes) + codes[:universe_extra]
    return SharpeRunCapture(run_id=run_id, base_rows=base_rows, risk_rows=risk_rows,
                            universe_codes=universe)


class TestPublishWeekBoard:
    WEEK = date(2026, 11, 2)  # 周一

    def _publish(self, db, capture, *, week=WEEK, source="stock", version="v1",
                 trigger="scheduled"):
        """指定周的周六北京时间 08:05 开始的任务发布"""
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        saturday = week + timedelta(days=5)
        started_at = datetime.combine(saturday, datetime.min.time(), tzinfo=tz) \
            + timedelta(hours=8, minutes=5)
        return sbs.publish_week_board(
            db, source=source, profile_version=version, capture=capture,
            trigger=trigger, started_at=started_at,
            finished_at=started_at + timedelta(hours=1),
        )

    def test_202_funds_all_recorded_deduped(self, db_session):
        """AC10：202 只入选基金全量记录且按 code 去重（不受 API 页长限制）"""
        codes = [f"{i:06d}" for i in range(1, 203)]
        cap = _qualified_capture("run-202", codes, universe_extra=2)  # universe 含重复
        row, written = self._publish(db_session, cap)
        assert written is True
        assert row.status == "complete"
        assert row.selected_count == 202
        assert db_session.query(SharpeBoardObservation).count() == 202
        obs_codes = {o.code for o in db_session.query(SharpeBoardObservation).all()}
        assert len(obs_codes) == 202 and obs_codes == set(codes)

    def test_observation_fields_snapshot(self, db_session):
        """观测快照：名称/有限 sharpe/计算时刻/样本尾日/天数/证据（筛选字段+刷新ID）"""
        cap = _qualified_capture("run-f1", ["300001"])
        cap.base_rows["300001"]["dd_3y"] = -12.5
        row, _ = self._publish(db_session, cap)
        obs = db_session.query(SharpeBoardObservation).one()
        assert obs.week_id == row.id
        assert obs.code == "300001"
        assert obs.name == "基金300001"
        assert obs.sharpe == 1.0
        assert obs.returns_end_date == date(2026, 10, 30)
        assert obs.sample_days == 746
        assert obs.metric_calculated_at == datetime(2026, 10, 31, 8, 40)  # UTC
        evidence = json.loads(obs.evidence_json)
        assert evidence["risk_run_id"] == "run-f1"
        assert evidence["base"]["dd_3y"] == -12.5

    def test_partial_failure_rolls_back_everything(self, db_session, monkeypatch):
        """一次事务写批次/观测：中途失败整体 rollback（库里无半个榜）"""
        codes = [f"{i:06d}" for i in range(1, 11)]
        cap = _qualified_capture("run-rb", codes)
        real_make = sbs._make_observation
        calls = {"n": 0}

        def flaky_make(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk boom mid-publish")
            return real_make(*a, **kw)

        monkeypatch.setattr(sbs, "_make_observation", flaky_make)
        with pytest.raises(RuntimeError):
            self._publish(db_session, cap)
        assert db_session.query(SharpeBoardWeek).count() == 0
        assert db_session.query(SharpeBoardObservation).count() == 0

    def test_complete_frozen_against_republish(self, db_session):
        """首次 complete 冻结：同周再发布不覆盖、不重复计次（AC8）"""
        cap = _qualified_capture("run-p1", ["300001"])
        row, _ = self._publish(db_session, cap)
        cap2 = _qualified_capture("run-p2", ["300001", "300002"])
        again, written = self._publish(db_session, cap2)
        assert written is False
        assert again.id == row.id
        assert db_session.query(SharpeBoardObservation).count() == 1
        reread = sbs.get_board_week(db_session, "stock", "v1", self.WEEK)
        assert reread.selected_count == 1

    def test_concurrent_unique_conflict_returns_existing_complete(self, db_session, monkeypatch):
        """并发唯一冲突：commit 冲突回滚后返回已有 complete，不重复写观测"""
        cap = _qualified_capture("run-c1", ["300001"])
        # 预插「并发方」已发布的同周榜
        self._publish(db_session, cap)
        real_get = sbs.get_board_week
        state = {"n": 0}

        def fake_get(db, source, version, week):
            state["n"] += 1
            if state["n"] == 1:
                return None  # 开头检查时并发行尚不可见
            return real_get(db, source, version, week)

        monkeypatch.setattr(sbs, "get_board_week", fake_get)
        real_commit = db_session.commit

        def flaky_commit():
            if state["n"] == 1:
                from sqlalchemy.exc import IntegrityError
                raise IntegrityError("stmt", {}, Exception("uq conflict"))
            real_commit()

        monkeypatch.setattr(db_session, "commit", flaky_commit)
        cap2 = _qualified_capture("run-c2", ["300001", "300002"])
        existing, written = self._publish(db_session, cap2)
        assert written is False
        assert existing.status == "complete"
        assert db_session.query(SharpeBoardObservation).count() == 1  # 保留首个

    def test_capture_errors_means_failed_no_observations(self, db_session):
        """capture.errors 非空（returned failed 漏报的网络失败）→ failed、零观测"""
        cap = _qualified_capture("run-e1", ["300001", "300002"])
        cap.add_error("risk:nav:300002: 东财网络超时")  # 库里有旧高夏普也不能用
        row, written = self._publish(db_session, cap)
        assert written is True
        assert row.status == "failed"
        assert row.published_at is None
        assert row.selected_count == 0
        assert db_session.query(SharpeBoardObservation).count() == 0
        assert json.loads(row.errors_json) == ["risk:nav:300002: 东财网络超时"]
        # 同周可成功重试
        cap2 = _qualified_capture("run-e2", ["300001"])
        row2, _ = self._publish(db_session, cap2)
        assert row2.status == "complete"
        assert row2.id == row.id  # 同一行覆盖重试

    def test_zero_selection_publishes_complete_empty_board(self, db_session):
        """有效全量输入零入选 → complete 空榜 selected_count=0（R6）"""
        cap = _qualified_capture("run-z1", ["300001"], sharpe=0.5)  # 低于 0.8
        row, written = self._publish(db_session, cap)
        assert written is True
        assert row.status == "complete"
        assert row.selected_count == 0
        assert row.published_at is not None
        assert db_session.query(SharpeBoardObservation).count() == 0

    def test_universe_empty_means_failed_not_empty_board(self, db_session):
        """采集范围为空（名单没抓到/预筛无命中）→ failed，不发空榜冒充零入选"""
        cap = SharpeRunCapture(run_id="run-u0")  # universe/base/risk 全空、无 errors
        row, written = self._publish(db_session, cap)
        assert written is True
        assert row.status == "failed"
        assert row.published_at is None
        assert json.loads(row.errors_json) == ["universe empty: no codes collected this run"]
        assert db_session.query(SharpeBoardObservation).count() == 0

    def test_all_stale_since_last_publish_skipped(self, db_session):
        """样本尾日相对上次发布无更新：全部无新增 → skipped_no_new_data"""
        cap1 = _qualified_capture("run-s1", ["300001"], end=date(2026, 10, 23))
        self._publish(db_session, cap1, week=date(2026, 10, 26))
        cap2 = _qualified_capture("run-s2", ["300001"], end=date(2026, 10, 23))
        row, written = self._publish(db_session, cap2, week=self.WEEK)
        assert written is True
        assert row.status == "skipped_no_new_data"
        assert row.selected_count == 0
        assert json.loads(row.diagnostics_json)["stale_codes"] == ["300001"]
        assert db_session.query(SharpeBoardObservation).count() == 1  # 仅上周观测

    def test_partial_stale_writes_fresh_only(self, db_session):
        """个别样本无更新：不写新点计诊断，更新的正常写"""
        cap1 = _qualified_capture("run-t1", ["300001", "300002"], end=date(2026, 10, 23))
        self._publish(db_session, cap1, week=date(2026, 10, 26))
        cap2 = _qualified_capture("run-t2", ["300001", "300002"], end=date(2026, 10, 30))
        cap2.risk_rows["300002"]["returns_end_date"] = date(2026, 10, 23)  # B 无更新
        row, _ = self._publish(db_session, cap2, week=self.WEEK)
        assert row.status == "complete"
        assert row.selected_count == 1
        obs = db_session.query(SharpeBoardObservation).all()
        assert {o.code for o in obs if o.week_id == row.id} == {"300001"}
        assert json.loads(row.diagnostics_json)["stale_codes"] == ["300002"]

    def test_first_publish_has_no_previous_so_all_written(self, db_session):
        """首次发布没有「上次」：全部入选者正常写点"""
        cap = _qualified_capture("run-f9", ["300001"], end=date(2026, 10, 30))
        row, _ = self._publish(db_session, cap)
        assert row.status == "complete"
        assert row.selected_count == 1

    def test_non_finite_sharpe_not_observed(self, db_session):
        """NaN/Infinity 不写观测：nan 过谓词（nan < X 恒 False）也会被有限检查兜住"""
        cap = _qualified_capture("run-i1", ["300001", "300002"])
        cap.risk_rows["300001"]["sharpe"] = float("nan")
        cap.risk_rows["300002"]["sharpe"] = float("inf")
        row, _ = self._publish(db_session, cap)
        assert row.status == "complete"
        assert row.selected_count == 0
        assert json.loads(row.diagnostics_json)["invalid_sharpe"] == ["300001", "300002"]
        assert db_session.query(SharpeBoardObservation).count() == 0

    def test_missing_evidence_diagnostics(self, db_session):
        """universe 有但 base/risk 缺失（无本轮证据）不参评、计诊断"""
        cap = _qualified_capture("run-m1", ["300001", "300002"])
        del cap.risk_rows["300002"]  # nav 失败的 code 无本轮风险证据
        row, _ = self._publish(db_session, cap)
        assert row.status == "complete"
        assert row.selected_count == 1
        assert json.loads(row.diagnostics_json)["missing_evidence"] == ["300002"]

    def test_market_source_subtype_membership_defense(self, db_session):
        """市场来源按规则副本 subtype 做成员防御过滤（不混入债 subtype）"""
        cap = _qualified_capture("run-d1", ["300001", "300002"])
        cap.base_rows["300002"]["market_subtype"] = "债券型-中短债"  # 不在股基 universe
        row, written = self._publish(db_session, cap, source="discovery-stock")
        assert written is True
        assert row.selected_count == 1
        obs = db_session.query(SharpeBoardObservation).one()
        assert obs.code == "300001"

    def test_recording_week_uses_started_at_not_finished(self, db_session):
        """跨周完成仍归开始周（AC5）：周键由 started_at 决定"""
        cap = _qualified_capture("run-w1", ["300001"])
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        started = datetime(2026, 10, 31, 8, 5, tzinfo=tz)  # 周六开始
        row, _ = sbs.publish_week_board(
            db_session, source="stock", profile_version="v1", capture=cap,
            trigger="scheduled", started_at=started,
            finished_at=started + timedelta(days=2),  # 周一才结束
        )
        assert row.week_start == date(2026, 10, 26)  # 开始周周一

    def test_sources_and_versions_isolated(self, db_session):
        """两来源独立发布同周（AC7 不混算）；未知版本发布被拒绝"""
        cap = _qualified_capture("run-x1", ["300001"])
        row1, w1 = self._publish(db_session, cap, source="stock")
        row2, w2 = self._publish(db_session, cap, source="discovery-stock")
        assert w1 and w2
        assert len({row1.id, row2.id}) == 2
        assert db_session.query(SharpeBoardWeek).count() == 2
        with pytest.raises(KeyError):
            self._publish(db_session, cap, version="v9")  # 真未知版本 → 拒绝发布

    def test_naive_started_at_rejected(self, db_session):
        cap = _qualified_capture("run-n1", ["300001"])
        with pytest.raises(ValueError):
            sbs.publish_week_board(
                db_session, source="stock", profile_version="v1", capture=cap,
                trigger="scheduled", started_at=datetime(2026, 10, 31, 8, 5),
            )

    def test_profile_snapshot_matches_version(self, db_session):
        """周行保存当版规则完整副本（canonical hash 一致）"""
        cap = _qualified_capture("run-h1", ["300001"])
        row, _ = self._publish(db_session, cap, source="discovery-stock")
        prof = sbs.get_profile("discovery-stock", "v1")
        assert row.profile_hash == sbs.canonical_hash(prof)
        assert row.algorithm_version == prof["algorithm_version"]


# ─────────────────────────────────────────────────────────────
# v2 profile（11-13-sharpe-board-v2-rules，AC1）
# ─────────────────────────────────────────────────────────────
class TestV2Profiles:
    def test_v2_profiles_exist_for_both_sources(self):
        assert sbs.get_profile("stock", "v2")["source"] == "stock"
        assert sbs.get_profile("discovery-stock", "v2")["source"] == "discovery-stock"

    def test_v2_filters_are_v1_plus_three_gates(self):
        v1 = sbs.get_profile("stock", "v1")["filters"]
        v2 = sbs.get_profile("stock", "v2")["filters"]
        # v1 五条件原封不动
        for k, v in v1.items():
            assert v2[k] == v, f"v2 丢失/篡改了 v1 条件 {k}"
        # 新增恰好三道门
        assert set(v2) - set(v1) == {"min_ir", "min_sample_days", "max_peer_pct"}
        assert v2["min_ir"] == 0.5
        assert v2["min_sample_days"] == 700
        assert v2["max_peer_pct"] == 20.0

    def test_v1_profile_not_polluted_by_v2(self):
        """AC1：v1 profile 必须仍是原始五条件，一字不改。"""
        expected = {
            "min_age": 3, "min_size_yi": 5, "max_dd_3y": 30,
            "min_mgr_exp": 5, "min_sharpe": 0.8, "exclude_qdii": False,
        }
        assert sbs.get_profile("stock", "v1")["filters"] == expected
        assert sbs.get_profile("discovery-stock", "v1")["filters"] == expected

    def test_v2_algorithm_version_bumped(self):
        v1_ver = sbs.get_profile("stock", "v1")["algorithm_version"]
        v2_ver = sbs.get_profile("stock", "v2")["algorithm_version"]
        assert v1_ver != v2_ver
        assert v2_ver == "risk-3y-v2"
        assert (v2_ver
                == sbs.get_profile("discovery-stock", "v2")["algorithm_version"])

    def test_v2_prefilters_and_subtypes_match_v1(self):
        for src in ("stock", "discovery-stock"):
            p1 = sbs.get_profile(src, "v1")
            p2 = sbs.get_profile(src, "v2")
            assert p2["collection_prefilters"] == p1["collection_prefilters"]
            assert p2["market_subtypes"] == p1["market_subtypes"]

    def test_profile_copies_are_independent(self):
        """深拷贝：改 v2 返回值不污染常量或 v1。"""
        p = sbs.get_profile("stock", "v2")
        p["filters"]["min_ir"] = 999
        assert sbs.get_profile("stock", "v2")["filters"]["min_ir"] == 0.5
        assert "min_ir" not in sbs.get_profile("stock", "v1")["filters"]


# ─────────────────────────────────────────────────────────────
# v2 发布（11-13-sharpe-board-v2-rules，AC3/AC5）：三道门 + gate_missing 诊断
# ─────────────────────────────────────────────────────────────
def _v2_capture(run_id: str, rows: dict[str, dict]) -> SharpeRunCapture:
    """v2 发布测试工厂。

    rows: code -> {base?, risk?, peer?}；缺省按「全部达标」填充。
    """
    base_rows, risk_rows, peer_rows = {}, {}, {}
    for code, spec in rows.items():
        base_rows[code] = {
            "name": f"基金{code}", "market_subtype": "股票型", "age_years": 6.0,
            "size_yi": 20.0, "mgr_experience_years": 8.0,
            "mgr_experience_years_max": 8.0, "dd_3y": -10.0,
            **(spec.get("base") or {}),
        }
        risk_rows[code] = {
            "sharpe": 1.0, "ir": 0.7, "sample_days": 746,
            "returns_end_date": date(2026, 10, 30),
            "calculated_at": datetime(2026, 10, 31, 8, 40, tzinfo=UTC),
            "benchmark_source": "fetched",
            **(spec.get("risk") or {}),
        }
        peer = spec.get("peer", {"peer_pct": 10.0, "peer_raw": "195/1951",
                                 "as_of": "2026-11-07"})
        if peer is not None:
            peer_rows[code] = peer
    return SharpeRunCapture(
        run_id=run_id, base_rows=base_rows, risk_rows=risk_rows,
        peer_rows=peer_rows, universe_codes=list(rows),
    )


class TestV2PublishGates:
    WEEK = date(2026, 11, 2)

    def _publish(self, db, capture, *, version="v2"):
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        started = datetime.combine(self.WEEK + timedelta(days=5),
                                   datetime.min.time(), tzinfo=tz) + timedelta(hours=8, minutes=5)
        return sbs.publish_week_board(
            db, source="stock", profile_version=version, capture=capture,
            trigger="scheduled", started_at=started,
            finished_at=started + timedelta(hours=1),
        )

    def test_all_gates_pass_writes_v2(self, db_session):
        cap = _v2_capture("run-v2a", {"400001": {}})
        row, written = self._publish(db_session, cap)
        assert written is True
        assert row.profile_version == "v2"
        assert row.algorithm_version == "risk-3y-v2"
        assert row.selected_count == 1
        obs = db_session.query(SharpeBoardObservation).all()
        assert len(obs) == 1
        ev = json.loads(obs[0].evidence_json)
        assert ev["peer"]["peer_pct"] == 10.0
        assert ev["risk"]["ir"] == 0.7
        assert ev["base"]["mgr_experience_years_max"] == 8.0

    def test_each_gate_blocks(self, db_session):
        """三道门任一不达标 / 数据缺失 → 不入榜。"""
        cap = _v2_capture("run-v2b", {
            "400010": {"risk": {"ir": 0.4}},               # IR 不达标
            "400011": {"risk": {"sample_days": 699}},      # 样本不足
            "400012": {"peer": {"peer_pct": 21.0}},        # 同类分位不达标
            "400013": {"risk": {"ir": None}},              # IR 缺失
            "400014": {"risk": {"sample_days": None}},    # 样本缺失
            "400015": {"peer": None},                      # peer 缺失
            "400016": {},                                  # 全部达标
        })
        row, _ = self._publish(db_session, cap, )
        assert row.selected_count == 1
        assert [o.code for o in db_session.query(SharpeBoardObservation).all()] == ["400016"]

    def test_gate_missing_diagnostics_only_missing(self, db_session):
        """AC5：诊断只记「数据缺失」，不记「不达标」（后者是正常筛选）。"""
        cap = _v2_capture("run-v2c", {
            "400020": {"risk": {"ir": None}},              # 缺失 → 诊断
            "400021": {"risk": {"ir": 0.4}},               # 不达标 → 不进诊断
            "400022": {"peer": None},                      # peer 缺失 → 诊断
            "400023": {"risk": {"sample_days": None}},     # 样本缺失 → 诊断
            "400024": {},                                  # 正常入选
        })
        row, _ = self._publish(db_session, cap)
        diag = json.loads(row.diagnostics_json)
        gm = diag["gate_missing"]
        assert set(gm["ir"]) == {"400020"}
        assert set(gm["sample_days"]) == {"400023"}
        assert set(gm["peer"]) == {"400022"}
        assert "400021" not in str(gm)     # 不达标不进诊断
        assert row.selected_count == 1

    def test_v1_profile_ignores_new_gates(self, db_session):
        """v1 profile 无三道门参数 → 缺 ir/peer 也不影响 v1 发布（向后兼容）。"""
        cap = _v2_capture("run-v2d", {
            "400030": {"risk": {"ir": None, "sample_days": None}, "peer": None},
        })
        row, _ = self._publish(db_session, cap, version="v1")
        assert row.profile_version == "v1"
        assert row.selected_count == 1
        diag = json.loads(row.diagnostics_json) if row.diagnostics_json else {}
        assert "gate_missing" not in diag


# ─────────────────────────────────────────────────────────────
# 52 周窗口与稳定性统计（11-13 任务 AC8/AC9b/AC9c）
# ─────────────────────────────────────────────────────────────
class TestFiftyTwoWeekWindow:
    """窗口只作用于聚合，不删除任何观测行。"""

    WEEK = date(2026, 11, 2)      # 作为「当前周」固定

    def _seed_weeks(self, db, weeks, *, code="500001", sharpe=1.0, version="v2"):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        for i, w in enumerate(weeks):
            row = SharpeBoardWeek(
                source="stock", profile_version=version, week_start=w,
                profile_json="{}", profile_hash="h",
                algorithm_version="risk-3y-v2", status="complete",
                selected_count=1,
                started_at=datetime.combine(w, datetime.min.time(), tzinfo=tz),
            )
            db.add(row)
            db.flush()
            db.add(SharpeBoardObservation(
                week_id=row.id, code=code, name=f"基金{code}", sharpe=sharpe,
                evidence_json=json.dumps({"peer": {"peer_pct": 12.5,
                                                   "as_of": "2026-11-07"}}),
            ))
        db.commit()

    def _agg(self, db, monkeypatch, **kw):
        monkeypatch.setattr(sbs, "_current_week", lambda: self.WEEK)
        return sbs.aggregate_board(db, source="stock", profile_version="v2", **kw)

    def test_100_weeks_history_capped_at_52(self, db_session, monkeypatch):
        weeks = [self.WEEK - timedelta(weeks=i) for i in range(100)][::-1]
        self._seed_weeks(db_session, weeks)
        body = self._agg(db_session, monkeypatch)
        it = body["items"][0]
        assert it["listed_weeks"] == 52
        assert it["consecutive_weeks"] == 52
        assert len(body["weeks"]) == 52
        assert body["weeks"][0] == self.WEEK - timedelta(weeks=51)
        assert (body["weeks"][-1] - body["weeks"][0]).days == 51 * 7
        assert all(w.weekday() == 0 for w in body["weeks"])
        # AC9c：窗口不删数据
        assert db_session.query(SharpeBoardObservation).count() == 100

    def test_history_shorter_than_52_uses_actual(self, db_session, monkeypatch):
        weeks = [self.WEEK - timedelta(weeks=i) for i in range(20)][::-1]
        self._seed_weeks(db_session, weeks)
        body = self._agg(db_session, monkeypatch)
        assert body["items"][0]["listed_weeks"] == 20
        assert len(body["weeks"]) == 20  # 不补零

    def test_window_excluded_fund_dropped_by_default(self, db_session, monkeypatch):
        """窗口外才有观测 → listed_weeks=0 → 默认 min_weeks=1 筛掉。"""
        # 该 code 只在 60 周前上榜，与窗口内另一只基金共存
        self._seed_weeks(db_session, [self.WEEK - timedelta(weeks=60)],
                         code="500002", version="v2")
        self._seed_weeks(db_session, [self.WEEK], code="500001", version="v2")
        body = self._agg(db_session, monkeypatch)
        assert [it["code"] for it in body["items"]] == ["500001"]
        # 显式 min_weeks=0 可以看到它，且统计为 0
        body0 = self._agg(db_session, monkeypatch, min_weeks=0)
        it2 = {it["code"]: it for it in body0["items"]}["500002"]
        assert it2["listed_weeks"] == 0
        assert it2["latest_sharpe"] is None

    def test_range_aliases_and_grid(self, db_session, monkeypatch):
        weeks = [self.WEEK - timedelta(weeks=i) for i in range(60)][::-1]
        self._seed_weeks(db_session, weeks)
        for key, expected_len in (("all", 52), ("1y", 52), ("6m", 26), ("3m", 13)):
            body = self._agg(db_session, monkeypatch, range_key=key)
            assert len(body["weeks"]) == expected_len, key
            assert all(w.weekday() == 0 for w in body["weeks"]), key
        assert (self._agg(db_session, monkeypatch, range_key="1y")["weeks"]
                == self._agg(db_session, monkeypatch, range_key="all")["weeks"])

    def test_near_12w_qualified(self, db_session, monkeypatch):
        """AC8：近12周达标统计，达标=sharpe>=0.8，分母=窗口内尾部12周。"""
        weeks = [self.WEEK - timedelta(weeks=i) for i in range(15)][::-1]
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        for i, w in enumerate(weeks):
            row = SharpeBoardWeek(
                source="stock", profile_version="v2", week_start=w,
                profile_json="{}", profile_hash="h",
                algorithm_version="risk-3y-v2", status="complete",
                selected_count=1,
                started_at=datetime.combine(w, datetime.min.time(), tzinfo=tz))
            db_session.add(row)
            db_session.flush()
            # 最近 12 周里 8 周达标（0.9），4 周不达标（0.5）；更早 3 周全达标
            sh = 0.5 if i >= 3 and (i - 3) % 3 == 0 else 0.9
            db_session.add(SharpeBoardObservation(week_id=row.id, code="500001",
                                                   name="基金500001", sharpe=sh))
        db_session.commit()
        body = self._agg(db_session, monkeypatch)
        it = body["items"][0]
        assert it["near_12w_total"] == 12
        assert it["near_12w_qualified"] == 8

    def test_near_12w_shorter_history(self, db_session, monkeypatch):
        weeks = [self.WEEK - timedelta(weeks=i) for i in range(6)][::-1]
        self._seed_weeks(db_session, weeks)
        it = self._agg(db_session, monkeypatch)["items"][0]
        assert it["near_12w_total"] == 6
        assert it["near_12w_qualified"] == 6

    def test_peer_display_from_evidence(self, db_session, monkeypatch):
        weeks = [self.WEEK - timedelta(weeks=i) for i in range(3)][::-1]
        self._seed_weeks(db_session, weeks)
        it = self._agg(db_session, monkeypatch)["items"][0]
        assert it["peer_pct"] == 12.5
        assert it["peer_as_of"] == "2026-11-07"


# ─────────────────────────────────────────────────────────────
# v3 profile（11-14-sharpe-board-v3-yearly-peer）
# ─────────────────────────────────────────────────────────────
class TestV3Profiles:
    WEEK = date(2026, 11, 2)

    def test_v3_profiles_exist(self):
        for src in ("stock", "discovery-stock"):
            assert sbs.get_profile(src, "v3")["source"] == src

    def test_v3_filters_use_yearly_peer_not_rolling(self):
        v3 = sbs.get_profile("stock", "v3")["filters"]
        # 年度口径两个参数
        assert v3["min_yearly_top_pct"] == 25.0
        assert v3["min_yearly_years"] == 2
        # 不再有滚动口径参数（两者语义不同，不可混用）
        assert "max_peer_pct" not in v3
        # v1 五条件 + v2 的 IR/样本门都保留
        for k, v in sbs.get_profile("stock", "v1")["filters"].items():
            assert v3[k] == v
        assert v3["min_ir"] == 0.5
        assert v3["min_sample_days"] == 700

    def test_v1_v2_not_polluted_by_v3(self):
        v1 = sbs.get_profile("stock", "v1")["filters"]
        v2 = sbs.get_profile("stock", "v2")["filters"]
        assert "min_yearly_top_pct" not in v1 and "min_yearly_years" not in v1
        assert "min_yearly_top_pct" not in v2 and "min_yearly_years" not in v2
        assert v2["max_peer_pct"] == 20.0   # v2 滚动口径原样
        assert v1 == {
            "min_age": 3, "min_size_yi": 5, "max_dd_3y": 30,
            "min_mgr_exp": 5, "min_sharpe": 0.8, "exclude_qdii": False,
        }

    def test_three_algorithm_versions_distinct(self):
        vs = {sbs.get_profile("stock", v)["algorithm_version"]
              for v in ("v1", "v2", "v3")}
        assert len(vs) == 3
        assert "risk-3y-v3" in vs

    def test_v3_inherits_prefilters_and_subtypes(self):
        for src in ("stock", "discovery-stock"):
            p2, p3 = sbs.get_profile(src, "v2"), sbs.get_profile(src, "v3")
            assert p3["collection_prefilters"] == p2["collection_prefilters"]
            assert p3["market_subtypes"] == p2["market_subtypes"]


class TestV3PublishGates:
    """v3 发布：年度达标才入选，且 evidence 存年度证据。"""

    WEEK = date(2026, 11, 2)

    def _publish(self, db, capture, version="v3"):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        started = datetime.combine(self.WEEK + timedelta(days=5),
                                   datetime.min.time(), tzinfo=tz) + timedelta(hours=8)
        return sbs.publish_week_board(
            db, source="stock", profile_version=version, capture=capture,
            trigger="scheduled", started_at=started,
            finished_at=started + timedelta(hours=1),
        )

    def _cap(self, rows):
        base, risk, peer = {}, {}, {}
        for code, spec in rows.items():
            base[code] = {
                "name": f"基金{code}", "market_subtype": "股票型",
                "age_years": 6.0, "size_yi": 20.0,
                "mgr_experience_years": 8.0, "mgr_experience_years_max": 8.0,
                "dd_3y": -10.0,
            }
            risk[code] = {
                "sharpe": 1.0, "ir": 0.7, "sample_days": 746,
                "returns_end_date": date(2026, 10, 30),
                "calculated_at": datetime(2026, 10, 31, 8, 40, tzinfo=UTC),
                "benchmark_source": "fetched",
            }
            p = spec.get("peer", "qualified")
            if p == "qualified":
                peer[code] = {
                    "years": {"2023": 10.0, "2024": 12.0, "2025": 15.0},
                    "qualified_years": 3, "yearly_top_pct": 25.0,
                    "min_years": 2, "qualified": True,
                    "window": ["2023", "2024", "2025"],
                }
            elif p == "partial":
                peer[code] = {
                    "years": {"2023": 10.0, "2024": 12.0, "2025": 80.0},
                    "qualified_years": 2, "yearly_top_pct": 25.0,
                    "min_years": 2, "qualified": True,
                    "window": ["2023", "2024", "2025"],
                }
            elif p == "fail":
                peer[code] = {
                    "years": {"2023": 90.0, "2024": 95.0, "2025": 80.0},
                    "qualified_years": 0, "yearly_top_pct": 25.0,
                    "min_years": 2, "qualified": False,
                    "window": ["2023", "2024", "2025"],
                }
        return SharpeRunCapture(
            run_id="run-v3", base_rows=base, risk_rows=risk,
            peer_rows=peer, universe_codes=list(rows),
        )

    def test_yearly_qualified_and_partial_both_pass(self, db_session):
        cap = self._cap({
            "900001": {"peer": "qualified"},
            "900002": {"peer": "partial"},   # 2/3 达标 → 通过
            "900003": {"peer": "fail"},      # 0/3 → 挡掉
        })
        row, _ = self._publish(db_session, cap)
        assert row.selected_count == 2
        codes = sorted(o.code for o in db_session.query(SharpeBoardObservation).all())
        assert codes == ["900001", "900002"]

    def test_evidence_stores_yearly_detail(self, db_session):
        cap = self._cap({"900010": {"peer": "partial"}})
        self._publish(db_session, cap)
        obs = db_session.query(SharpeBoardObservation).one()
        ev = json.loads(obs.evidence_json)
        assert ev["peer"]["qualified_years"] == 2
        assert ev["peer"]["window"] == ["2023", "2024", "2025"]
        assert ev["peer"]["years"]["2025"] == 80.0

    def test_no_peer_evidence_blocked_and_diagnosed(self, db_session):
        """无年度数据：既不入选，也不进 gate_missing（因为不在 peer_rows 里）。"""
        cap = self._cap({"900020": {"peer": None}})
        row, _ = self._publish(db_session, cap)
        assert row.selected_count == 0

    def test_v2_profile_ignores_yearly_params(self, db_session):
        """v2 profile 无 min_yearly_years → 年度不达标也不影响 v2 发布。"""
        cap = self._cap({"900030": {"peer": "fail"}})
        # v2 需要 peer_pct 字段，这里补一个合格值
        cap.peer_rows["900030"]["peer_pct"] = 10.0
        row, _ = self._publish(db_session, cap, version="v2")
        assert row.profile_version == "v2"
        assert row.selected_count == 1


class TestAggregateSourceAll:
    """source=all 聚合两条链路的观测（11-15-source-segmented 回归）。"""

    WEEK = date(2026, 11, 2)

    def _seed(self, db, code, sharpe, *, source):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        row = SharpeBoardWeek(
            source=source, profile_version="v3", week_start=self.WEEK,
            profile_json="{}", profile_hash="h",
            algorithm_version="risk-3y-v3", status="complete",
            selected_count=1,
            started_at=datetime.combine(self.WEEK, datetime.min.time(), tzinfo=tz),
        )
        db.add(row)
        db.flush()
        db.add(SharpeBoardObservation(
            week_id=row.id, code=code, name=f"基金{code}", sharpe=sharpe,
            evidence_json=json.dumps({"peer": {"peer_pct": 12.5, "as_of": "2026-11-07"}}),
        ))
        db.commit()

    def test_all_merges_both_sources(self, db_session, monkeypatch):
        """同名基金两条链路同一周都上榜 → 一周只算一次（stock 口径为准）。"""
        self._seed(db_session, "500001", 0.9, source="stock")
        self._seed(db_session, "500001", 1.1, source="discovery-stock")
        monkeypatch.setattr(sbs, "_current_week", lambda: self.WEEK)
        body = sbs.aggregate_board(db_session, source="all", profile_version="v3")
        assert body["profile"]["source"] == "all"
        assert body["total"] == 1
        it = body["items"][0]
        assert it["code"] == "500001"
        assert it["listed_weeks"] == 1
        assert it["latest_sharpe"] == 0.9  # 同周取三分法观测

    def test_all_distinct_weeks_accumulate(self, db_session, monkeypatch):
        """同名基金两条链路不同周 → 两周都算（跨来源累计）。"""
        self._seed(db_session, "500001", 0.9, source="stock")
        # 第二条 seed 改到上一周
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        prev_week = self.WEEK - timedelta(weeks=1)
        row = SharpeBoardWeek(
            source="discovery-stock", profile_version="v3", week_start=prev_week,
            profile_json="{}", profile_hash="h",
            algorithm_version="risk-3y-v3", status="complete",
            selected_count=1,
            started_at=datetime.combine(prev_week, datetime.min.time(), tzinfo=tz),
        )
        db_session.add(row)
        db_session.flush()
        db_session.add(SharpeBoardObservation(
            week_id=row.id, code="500001", name="基金500001", sharpe=1.1,
            evidence_json=json.dumps({"peer": {"peer_pct": 12.5, "as_of": "2026-11-07"}}),
        ))
        db_session.commit()
        monkeypatch.setattr(sbs, "_current_week", lambda: self.WEEK)
        body = sbs.aggregate_board(db_session, source="all", profile_version="v3")
        it = body["items"][0]
        assert it["listed_weeks"] == 2
        assert it["consecutive_weeks"] == 2

    def test_all_union_of_distinct_codes(self, db_session, monkeypatch):
        """不同基金分属两条链路 → all 态并集都出现。"""
        self._seed(db_session, "500001", 0.9, source="stock")
        self._seed(db_session, "500002", 1.2, source="discovery-stock")
        monkeypatch.setattr(sbs, "_current_week", lambda: self.WEEK)
        body = sbs.aggregate_board(db_session, source="all", profile_version="v3")
        assert {it["code"] for it in body["items"]} == {"500001", "500002"}
