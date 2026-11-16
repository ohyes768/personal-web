"""经理月度刷新任务（managers_refresh.py）：锁互斥、状态口径、历史落盘。"""
import json
import threading
from unittest.mock import Mock

import pytest

from src.scheduler import managers_refresh as mod
from src.scheduler import weekly_refresh as weekly

JOB_ID = 'monthly_managers_refresh'


class _BusyLock:
    """模拟手动刷新占用中：acquire 永远失败"""

    def acquire(self, blocking=False):
        return False

    def release(self):
        pass


@pytest.fixture
def free_lock(monkeypatch):
    """替换真锁为一个测试锁，默认可获取，测试内可控"""
    lock = threading.Lock()
    monkeypatch.setattr('src.api.manager_routes._refresh_lock', lock)
    return lock


def test_skipped_when_manual_refresh_holds_lock(monkeypatch, tmp_path):
    """手动刷新进行中 → 定时轮跳过，不发起采集（双跑防重）"""
    monkeypatch.setattr('src.api.manager_routes._refresh_lock', _BusyLock())
    collector = Mock()
    monkeypatch.setattr('src.services.manager_refresh.refresh', collector)
    path = tmp_path / 'h.jsonl'
    result = mod.refresh_managers_sync(job_id=JOB_ID, history_path=path, trigger='scheduled')
    collector.assert_not_called()
    assert result['status'] == 'skipped'
    assert result['items'][0]['status'] == 'skipped'
    assert '手动刷新' in result['items'][0]['error']
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['status'] == 'skipped'


def test_success_records_history_and_closes_session(monkeypatch, tmp_path, free_lock):
    """采集成功 → success，结果与 JSONL 一致；session 正常关闭"""
    monkeypatch.setattr('src.services.manager_refresh.refresh',
                        Mock(return_value={'managers_total': 5, 'failed': 0}))
    sessions = []
    import src.db.session as db_session_mod

    class FakeDb:
        def close(self):
            sessions.append(True)

    monkeypatch.setattr(db_session_mod, 'SessionLocal', lambda: FakeDb())
    path = tmp_path / 'h.jsonl'
    result = mod.refresh_managers_sync(job_id=JOB_ID, history_path=path, trigger='scheduled', run_id='r1')
    assert result['status'] == 'success'
    assert result['items'][0]['result'] == {'managers_total': 5, 'failed': 0}
    assert result['run_id'] == 'r1'
    assert sessions == [True]
    assert json.loads(path.read_text(encoding='utf-8')) == result


def test_partial_when_some_managers_failed(monkeypatch, tmp_path, free_lock):
    """有人重试 3 次仍失败 → partial（明细在 result.errors），不是 failed"""
    monkeypatch.setattr('src.services.manager_refresh.refresh',
                        Mock(return_value={'managers_total': 5, 'failed': 2,
                                           'errors': ['30189744: timeout']}))
    import src.db.session as db_session_mod

    class FakeDb:
        def close(self):
            pass

    monkeypatch.setattr(db_session_mod, 'SessionLocal', lambda: FakeDb())
    result = mod.refresh_managers_sync(job_id=JOB_ID, history_path=tmp_path / 'h.jsonl')
    assert result['status'] == 'partial'


def test_collector_exception_marks_failed(monkeypatch, tmp_path, free_lock):
    """编排抛异常 → failed，锁仍释放（不卡死后续手动刷新）"""
    monkeypatch.setattr('src.services.manager_refresh.refresh',
                        Mock(side_effect=RuntimeError('db offline')))
    import src.db.session as db_session_mod

    class FakeDb:
        def close(self):
            pass

    monkeypatch.setattr(db_session_mod, 'SessionLocal', lambda: FakeDb())
    result = mod.refresh_managers_sync(job_id=JOB_ID, history_path=tmp_path / 'h.jsonl')
    assert result['status'] == 'failed'
    assert 'db offline' in result['items'][0]['error']
    # 锁已释放：立即再获取应成功
    assert free_lock.acquire(blocking=False)
    free_lock.release()


def test_history_path_defaults_to_shared_jsonl(monkeypatch, tmp_path):
    """不传 history_path 时落 DATA_DIR/scheduler/weekly_refresh.jsonl（弹窗历史共用）"""
    monkeypatch.setattr(mod, 'HISTORY_PATH', tmp_path / 'scheduler' / 'weekly_refresh.jsonl')
    monkeypatch.setattr('src.api.manager_routes._refresh_lock', _BusyLock())
    mod.refresh_managers_sync(job_id=JOB_ID, trigger='scheduled')
    saved = json.loads((tmp_path / 'scheduler' / 'weekly_refresh.jsonl').read_text(encoding='utf-8'))
    assert saved['job_id'] == JOB_ID and saved['items'][0]['tab'] == 'managers'


def test_dispatch_routes_managers_target(monkeypatch, tmp_path):
    """调度器分发：target=refresh_managers 走 refresh_managers_sync，不带 tab kwarg"""
    calls = []

    def fake_managers(**kwargs):
        calls.append(('managers', kwargs))
        return {'status': 'success', 'items': []}

    monkeypatch.setattr('src.scheduler.managers_refresh.refresh_managers_sync', fake_managers)

    import asyncio
    from src.scheduler.manager import SchedulerManager

    async def scenario():
        instance = SchedulerManager(state_dir=tmp_path)
        monkeypatch.setattr(instance.scheduler, 'start', Mock())
        instance.start(None)
        try:
            await instance.trigger_now('monthly_managers_refresh')
            await asyncio.gather(*instance._background_tasks)
            await instance.shutdown()
        finally:
            await asyncio.sleep(0)
        return instance

    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop)
    assert len(calls) == 1 and calls[0][0] == 'managers'
    assert 'tab' not in calls[0][1]
    assert calls[0][1]['job_id'] == 'monthly_managers_refresh'
