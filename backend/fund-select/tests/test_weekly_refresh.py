"""Four independent weekly jobs: schedule, collector isolation, and persistence."""
import json
from datetime import datetime
from unittest.mock import ANY, Mock
from zoneinfo import ZoneInfo

import pytest

from src.scheduler.manager import SchedulerManager

IDS = ['weekly_bond_refresh', 'weekly_stock_refresh', 'weekly_discovery_bond_refresh', 'weekly_discovery_stock_refresh']
TABS = ['bond', 'stock', 'discovery-bond', 'discovery-stock']


def test_four_staggered_weekly_jobs(monkeypatch, tmp_path):
    manager = SchedulerManager(state_dir=tmp_path)
    monkeypatch.setattr(manager.scheduler, 'start', Mock())
    manager.start(None)
    jobs = manager.scheduler.get_jobs()
    assert [job.id for job in jobs] == IDS
    now = datetime(2026, 10, 29, 12, tzinfo=ZoneInfo('Asia/Shanghai'))
    for hour, job in zip(range(7, 11), jobs):
        assert job.trigger.get_next_fire_time(None, now).isoformat() == f'2026-10-31T{hour:02}:05:00+08:00'
        assert job.max_instances == 1 and job.coalesce is True
        assert job.misfire_grace_time == 3600
    assert [j['tab'] for j in manager.list_jobs()] == TABS


@pytest.mark.parametrize('tab,job_id', list(zip(TABS, IDS)))
def test_refresh_calls_only_its_collector(monkeypatch, tmp_path, tab, job_id):
    from src.scheduler import weekly_refresh as weekly
    from src.data.market_subtype_map import DISCOVERY_BOND_SUBTYPES, DISCOVERY_STOCK_SUBTYPES
    collectors = [Mock(return_value={'completed': 2, 'failed': 0}) for _ in range(3)]
    for name, mock in zip(['refresh_configured_funds_sync', 'refresh_stock_funds_sync', 'refresh_market_full_sync'], collectors):
        monkeypatch.setattr(weekly, name, mock)
    monkeypatch.setattr(weekly, '_publish_capture', Mock(return_value='complete'))
    path = tmp_path / 'history.jsonl'
    snapshots = []
    result = weekly.refresh_tab_sync(tab=tab, job_id=job_id, history_path=path, trigger='manual', on_progress=snapshots.append)
    selected = 0 if tab == 'bond' else 1 if tab == 'stock' else 2
    assert [mock.call_count for mock in collectors] == [int(i == selected) for i in range(3)]
    if selected < 2:
        # stock tab 周任务额外收 capture kwarg（夏普周榜冻结），bond 不接
        kwargs = {'use_cache': False}
        if tab == 'stock':
            kwargs['capture'] = ANY
        collectors[selected].assert_called_once_with(**kwargs)
    else:
        bond = tab == 'discovery-bond'
        kwargs = dict(
            universe_filter=list(DISCOVERY_BOND_SUBTYPES if bond else DISCOVERY_STOCK_SUBTYPES),
            pipeline_profile='bond' if bond else 'stock', min_ret_3y=10 if bond else 20,
            min_size_yi=5, min_mgr_exp=5,
        )
        if tab == 'discovery-stock':
            kwargs['capture'] = ANY
        collectors[selected].assert_called_once_with(**kwargs)
    assert result['job_id'] == job_id and result['status'] == 'success'
    assert len(result['items']) == 1 and result['items'][0]['tab'] == tab
    assert result['start'].endswith('+08:00') and result['end'].endswith('+08:00')
    assert snapshots[0]['status'] == 'running'
    if tab in ('stock', 'discovery-stock'):
        assert result['snapshot_status'] == 'complete'
    else:
        assert 'snapshot_status' not in result
    assert json.loads(path.read_text(encoding='utf-8')) == result
    weekly.refresh_tab_sync(tab=tab, job_id=job_id, history_path=path)
    assert len(path.read_text(encoding='utf-8').splitlines()) == 2


def test_collector_exception_is_recorded(monkeypatch, tmp_path):
    from src.scheduler import weekly_refresh as weekly
    monkeypatch.setattr(weekly, 'refresh_configured_funds_sync', Mock(side_effect=RuntimeError('offline')))
    result = weekly.refresh_tab_sync(tab='bond', job_id=IDS[0], history_path=tmp_path / 'history.jsonl')
    assert result['status'] == 'failed' and result['items'][0]['error'] == 'offline'


@pytest.mark.parametrize('result,expected', [
    ({'completed': 0, 'failed': 3}, 'failed'),
    ({'total': 0, 'completed': 0, 'failed': 0}, 'failed'),
    ({'stage_results': {'L1': {'status': 'done', 'result': {'failed': 2, 'inserted': 3, 'updated': 1, 'total': 6}}}}, 'partial'),
    ({'stage_results': {'L1': {'status': 'done', 'result': {'failed': 2, 'completed': 3}}}}, 'partial'),
    ({'stage_results': {'L1': {'status': 'error'}}}, 'failed'),
    ({'stage_results': {'L0': {'status': 'done'}, 'L1': {'status': 'error'}}}, 'partial'),
])
def test_classify_result(result, expected):
    from src.scheduler.weekly_refresh import classify_result
    assert classify_result(result) == expected


# ─────────────────────────────────────────────────────────────
# 夏普周榜发布接线（implement 步骤 3：仅 stock / discovery-stock 发布）
# ─────────────────────────────────────────────────────────────

def _fill_capture(cap):
    """collector mock 内填充本轮冻结数据（单只合格入选）"""
    cap.universe_codes = ['300001']
    cap.base_rows['300001'] = {
        'name': '股基300001', 'market_subtype': '股票型', 'age_years': 6.0,
        'size_yi': 20.0, 'mgr_experience_years': 8.0, 'dd_3y': -10.0,
    }
    cap.risk_rows['300001'] = {
        'sharpe': 1.1, 'sample_days': 746, 'returns_end_date': None,
        'benchmark_source': 'fetched',
    }


@pytest.mark.parametrize('tab,source', [('stock', 'stock'),
                                        ('discovery-stock', 'discovery-stock')])
def test_stock_tabs_capture_and_publish(monkeypatch, tmp_path, tab, source):
    """两条股基任务接 capture + 发布：同一 capture 传给 collector 与发布；trigger 透传"""
    from src.scheduler import weekly_refresh as weekly

    collector_capture = {}

    def fake_collector(**kwargs):
        collector_capture['capture'] = kwargs.get('capture')
        _fill_capture(kwargs['capture'])
        return {'completed': 1, 'failed': 0}

    if tab == 'stock':
        monkeypatch.setattr(weekly, 'refresh_stock_funds_sync', fake_collector)
    else:
        monkeypatch.setattr(weekly, 'refresh_market_full_sync', fake_collector)

    published = {}

    def fake_publish(**kwargs):
        published.update(kwargs)
        return 'complete'  # 真实 _publish_capture 返回周行状态字符串

    monkeypatch.setattr(weekly, '_publish_capture', fake_publish)
    result = weekly.refresh_tab_sync(tab=tab, job_id=f'weekly_{tab}_refresh',
                                     history_path=tmp_path / 'history.jsonl',
                                     trigger='manual', run_id='run-x1')

    cap = collector_capture['capture']
    assert cap is not None and cap.universe_codes == ['300001']
    # 规则条件来自固定 profile（后台规则，不读浏览器临时条件）
    assert cap.filters['min_sharpe'] == 0.8 and cap.filters['min_age'] == 3
    assert published['source'] == source
    assert published['capture'] is cap
    assert published['trigger'] == 'manual'
    assert published['profile_version'] == 'v1'
    assert published['started_at'].tzinfo is not None  # 周键需要 aware
    assert published['started_at'] <= published['finished_at']
    assert result['snapshot_status'] == 'complete'
    assert result['status'] == 'success'  # collector 成功结果不被发布覆盖
    # run_id 透传给周行（关联本轮 JSONL 审计记录）
    assert cap.run_id == 'run-x1'


@pytest.mark.parametrize('tab', ['bond', 'discovery-bond'])
def test_bond_tabs_never_capture_or_publish(monkeypatch, tmp_path, tab):
    """bond 两条既不接 capture 也不发布（现有债基刷新不算夏普，PRD）"""
    from unittest.mock import Mock
    from src.scheduler import weekly_refresh as weekly

    publish_mock = Mock()
    monkeypatch.setattr(weekly, '_publish_capture', publish_mock)
    collector = Mock(return_value={'completed': 1, 'failed': 0})
    name = 'refresh_configured_funds_sync' if tab == 'bond' else 'refresh_market_full_sync'
    monkeypatch.setattr(weekly, name, collector)

    result = weekly.refresh_tab_sync(tab=tab, job_id='x', history_path=tmp_path / 'h.jsonl')

    publish_mock.assert_not_called()
    _, kwargs = collector.call_args
    assert 'capture' not in kwargs
    assert 'snapshot_status' not in result


def test_publish_failure_isolated(monkeypatch, tmp_path):
    """发布抛错 → 真实 _publish_capture 吞掉返回 failed，collector 成功结果与 JSONL 审计保留"""
    from src.db import session as db_session_mod
    from src.scheduler import weekly_refresh as weekly
    from src.services import sharpe_board_service as sbs

    monkeypatch.setattr(weekly, 'refresh_stock_funds_sync',
                        Mock(return_value={'completed': 2, 'failed': 0}))

    class FakeDb:
        def close(self):
            pass

    monkeypatch.setattr(db_session_mod, 'SessionLocal', lambda: FakeDb())

    def boom(db, **kwargs):
        raise RuntimeError('db locked mid-publish')

    monkeypatch.setattr(sbs, 'publish_week_board', boom)
    path = tmp_path / 'history.jsonl'
    result = weekly.refresh_tab_sync(tab='stock', job_id=IDS[1], history_path=path,
                                     trigger='scheduled', run_id='run-x2')
    assert result['snapshot_status'] == 'failed'
    assert result['status'] == 'success'  # collector 结果保留
    assert result['items'][0]['status'] == 'success'
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['snapshot_status'] == 'failed'


def test_run_id_falls_back_to_uuid_when_missing(monkeypatch, tmp_path):
    """run_id=None（测试直调）时 capture.run_id 兜底 uuid，不为空"""
    from src.scheduler import weekly_refresh as weekly
    from unittest.mock import Mock

    monkeypatch.setattr(weekly, 'refresh_stock_funds_sync',
                        Mock(return_value={'completed': 0, 'failed': 0}))
    monkeypatch.setattr(weekly, '_publish_capture', Mock(return_value='complete'))
    result = weekly.refresh_tab_sync(tab='stock', job_id=IDS[1],
                                     history_path=tmp_path / 'h.jsonl')
    assert result['snapshot_status'] == 'complete'


def test_collector_crash_marks_capture_failed(monkeypatch, tmp_path):
    """collector 整体崩溃：崩溃证据补进 capture.errors，发布收到失败信号（R6），
    不误发 complete 空榜冒充零入选"""
    from src.scheduler import weekly_refresh as weekly

    def crashing(**kwargs):
        raise RuntimeError('boom mid-collect')

    monkeypatch.setattr(weekly, 'refresh_stock_funds_sync', crashing)
    published = {}

    def fake_publish(**kwargs):
        published.update(kwargs)
        return 'failed'

    monkeypatch.setattr(weekly, '_publish_capture', fake_publish)
    result = weekly.refresh_tab_sync(tab='stock', job_id=IDS[1],
                                     history_path=tmp_path / 'h.jsonl')
    assert result['status'] == 'failed'
    assert result['snapshot_status'] == 'failed'
    assert any('collector crashed' in e for e in published['capture'].errors)


class TestPublishCaptureIsolation:
    """_publish_capture 本体：发布异常吞掉返回 failed（不阻断队列）"""

    def test_exception_returns_failed(self, monkeypatch):
        from src.db import session as db_session_mod
        from datetime import UTC, datetime
        from src.scheduler import weekly_refresh as weekly
        from src.services import sharpe_board_service as sbs
        from src.services.sharpe_capture import SharpeRunCapture

        class FakeDb:
            def close(self):
                pass

        monkeypatch.setattr(db_session_mod, 'SessionLocal', lambda: FakeDb())

        def boom(db, **kwargs):
            raise RuntimeError('publish boom')

        monkeypatch.setattr(sbs, 'publish_week_board', boom)
        status = weekly._publish_capture(
            source='stock', capture=SharpeRunCapture(run_id='r'),
            trigger='scheduled',
            started_at=datetime(2026, 10, 31, 8, 5, tzinfo=UTC),
            finished_at=datetime(2026, 10, 31, 9, 5, tzinfo=UTC),
        )
        assert status == 'failed'
