"""
夏普榜单步骤 1 测试：唯一约束 / 重启保留 / 规则 profile / 周键 / 冻结语义

对应 implement.md 步骤 1（AC5、AC7、AC8）：
- 同 source/version/week 两行失败，不同 source/version 可共存
- tmp_path 文件 SQLite：重新开连接数据仍在
- recording_week 跨年/跨周/时区/naive 拒绝
- complete 零入选、failed、skipped_no_new_data 三种状态区分；complete 同周重试不覆盖
"""
import json
from datetime import UTC, date, datetime

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
            self._publish(db_session, cap, version="v2")  # 无 v2 profile → 拒绝发布

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
