"""Per-tab settings/history, duplicate protection, and shared collection queue."""
import asyncio
import json
import threading
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.scheduler.manager import SchedulerManager

IDS = ['weekly_bond_refresh', 'weekly_stock_refresh', 'weekly_discovery_bond_refresh', 'weekly_discovery_stock_refresh']


@pytest.fixture
def manager(tmp_path, monkeypatch):
    instance = SchedulerManager(state_dir=tmp_path)
    monkeypatch.setattr(instance.scheduler, 'start', Mock())
    instance.start(None)
    return instance


@pytest.fixture
def client(manager):
    from src.scheduler.routes import router
    app = FastAPI()
    app.state.scheduler = manager
    app.include_router(router, prefix='/api/funds')
    return TestClient(app)


def test_pause_is_independent_and_persistent(client, manager, tmp_path, monkeypatch):
    jobs = client.get('/api/funds/scheduler/jobs').json()['jobs']
    assert len(jobs) == 4 and all(j['enabled'] for j in jobs)
    assert client.patch(f'/api/funds/scheduler/jobs/{IDS[0]}', json={'enabled': False}).status_code == 200
    second = SchedulerManager(state_dir=tmp_path)
    monkeypatch.setattr(second.scheduler, 'start', Mock())
    second.start(None)
    assert [j['enabled'] for j in second.list_jobs()] == [False, True, True, True]
    assert second.list_jobs()[0]['next_run_time'] is None


def test_old_disabled_setting_migrates_to_all_tabs(tmp_path, monkeypatch):
    (tmp_path / 'settings.json').write_text(json.dumps({'weekly_fund_refresh': False, IDS[1]: True}))
    instance = SchedulerManager(state_dir=tmp_path)
    monkeypatch.setattr(instance.scheduler, 'start', Mock())
    instance.start(None)
    assert [j['enabled'] for j in instance.list_jobs()] == [False, True, False, False]


def test_write_failure_keeps_state(client, manager, monkeypatch):
    monkeypatch.setattr(manager, '_save_settings', Mock(side_effect=OSError('disk full')))
    assert client.patch(f'/api/funds/scheduler/jobs/{IDS[0]}', json={'enabled': False}).status_code == 503
    assert all(j['enabled'] for j in manager.list_jobs())


def test_history_isolated_and_old_group_projected_per_tab(client, manager):
    old = {'job_id': 'weekly_fund_refresh', 'status': 'partial', 'start': 'old', 'items': [
        {'tab': 'bond', 'status': 'success', 'start': 'bond-start', 'end': 'bond-end'},
        {'tab': 'stock', 'status': 'failed', 'start': 'stock-start', 'end': 'stock-end', 'error': 'offline'},
    ]}
    own = {'job_id': IDS[0], 'status': 'partial', 'start': 'new', 'items': [{'tab': 'bond'}]}
    manager.history_path.write_text(json.dumps(old) + '\ninvalid\n' + json.dumps(own) + '\n', encoding='utf-8')
    bond = client.get(f'/api/funds/scheduler/jobs/{IDS[0]}/runs').json()['runs']
    stock = client.get(f'/api/funds/scheduler/jobs/{IDS[1]}/runs').json()['runs']
    assert [r['status'] for r in bond] == ['partial', 'success']
    assert bond[1]['start'] == 'bond-start' and len(bond[1]['items']) == 1
    assert len(stock) == 1 and stock[0]['status'] == 'failed'
    assert manager.get_job_runs(IDS[2]) == []
    assert client.get(f'/api/funds/scheduler/jobs/{IDS[0]}/runs?limit=1').json()['runs'] == [own]


def test_unknown_and_conflicting_requests(client, manager, monkeypatch):
    assert client.patch('/api/funds/scheduler/jobs/missing', json={'enabled': False}).status_code == 404
    assert client.post('/api/funds/scheduler/jobs/missing/run').status_code == 404
    assert client.get('/api/funds/scheduler/jobs/missing/runs').status_code == 404
    assert client.get(f'/api/funds/scheduler/jobs/{IDS[0]}/runs?limit=0').status_code == 422
    async def conflict(job_id):
        raise ValueError('任务正在运行')
    monkeypatch.setattr(manager, 'trigger_now', conflict)
    assert client.post(f'/api/funds/scheduler/jobs/{IDS[0]}/run').status_code == 409


def test_separate_jobs_queue_without_overlap_or_duplicate(tmp_path, monkeypatch):
    from src.scheduler import weekly_refresh
    release = threading.Event()
    started = threading.Event()
    order = []
    caller_thread = threading.get_ident()

    def collect(**kwargs):
        assert threading.get_ident() != caller_thread
        order.append(kwargs['tab'])
        if len(order) == 1:
            started.set()
            assert release.wait(5)
            raise OSError('first job failed')
        return {'status': 'success', 'items': []}

    monkeypatch.setattr(weekly_refresh, 'refresh_tab_sync', collect)

    async def scenario():
        instance = SchedulerManager(state_dir=tmp_path)
        instance.start(None)
        try:
            await instance.trigger_now(IDS[0])
            assert await asyncio.to_thread(started.wait, 5)
            with pytest.raises(ValueError, match='运行'):
                await instance.trigger_now(IDS[0])
            await instance._run_scheduled(IDS[0])
            instance.set_enabled(IDS[1], False)
            await instance.trigger_now(IDS[1])
            await asyncio.sleep(0)
            jobs = instance.list_jobs()
            assert jobs[0]['running'] and jobs[1]['running']
            assert jobs[1]['current_run']['status'] == 'queued'
            assert not jobs[2]['running'] and order == ['bond']
        finally:
            release.set()
            await asyncio.gather(*instance._background_tasks)
            await instance.shutdown()
            await asyncio.sleep(0)
        assert order == ['bond', 'stock']
        assert not any(j['running'] for j in instance.list_jobs())
        assert instance.list_jobs()[0]['last_run']['error'] == 'first job failed'
        assert instance.list_jobs()[1]['last_run']['status'] == 'success'

    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop)
