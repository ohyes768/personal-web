"""Four independent weekly jobs: schedule, collector isolation, and persistence."""
import json
from datetime import datetime
from unittest.mock import Mock
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
    path = tmp_path / 'history.jsonl'
    snapshots = []
    result = weekly.refresh_tab_sync(tab=tab, job_id=job_id, history_path=path, trigger='manual', on_progress=snapshots.append)
    selected = 0 if tab == 'bond' else 1 if tab == 'stock' else 2
    assert [mock.call_count for mock in collectors] == [int(i == selected) for i in range(3)]
    if selected < 2:
        collectors[selected].assert_called_once_with(use_cache=False)
    else:
        bond = tab == 'discovery-bond'
        collectors[selected].assert_called_once_with(
            universe_filter=list(DISCOVERY_BOND_SUBTYPES if bond else DISCOVERY_STOCK_SUBTYPES),
            pipeline_profile='bond' if bond else 'stock', min_ret_3y=10 if bond else 20,
            min_size_yi=5, min_mgr_exp=5,
        )
    assert result['job_id'] == job_id and result['status'] == 'success'
    assert len(result['items']) == 1 and result['items'][0]['tab'] == tab
    assert result['start'].endswith('+08:00') and result['end'].endswith('+08:00')
    assert snapshots[0]['status'] == 'running'
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
