import asyncio
import threading
import time
import pytest

from src.services.refresh_jobs import RefreshJobManager


def test_background_dedup_progress_and_restart(tmp_path):
    async def scenario():
        manager = RefreshJobManager(tmp_path)
        gate = threading.Event()
        def work(progress):
            gate.wait(120)  # A potentially >60s collector; release after checking acceptance.
            progress('000090', True)
            progress('600000', False)
        started = time.monotonic()
        job = manager.submit('m120', ['000090', '600000'], work)
        assert time.monotonic() - started < 0.2
        assert manager.submit('m120', [], work)['job_id'] == job['job_id']
        assert manager.latest('m120')['remaining'] == 2
        gate.set()
        await manager.close(timeout=2)
        result = manager.get(job['job_id'])
        assert result['status'] == 'partial_failed'
        assert (result['processed'], result['succeeded'], result['failed'], result['remaining']) == (2, 1, 1, 0)
        assert result['retry_codes'] == ['600000']
        assert RefreshJobManager(tmp_path).latest('m120')['status'] == 'partial_failed'
    asyncio.run(scenario())


@pytest.mark.parametrize('successes,status', [(0, 'failed'), (1, 'partial_failed'), (2, 'succeeded')])
def test_result_counts_and_empty_job(tmp_path, successes, status):
    async def scenario():
        manager = RefreshJobManager(tmp_path)
        def work(progress):
            for i, code in enumerate(['000090', '600000']):
                progress(code, i < successes)
        job = manager.submit('financial', ['000090', '600000'], work)
        await manager.close(timeout=2)
        result = manager.get(job['job_id'])
        assert result['status'] == status
        assert result['succeeded'] == successes
        assert result['failed'] == 2 - successes
        empty_manager = RefreshJobManager(tmp_path / 'empty')
        empty = empty_manager.submit('financial', [], lambda p: None)
        await empty_manager.close(timeout=2)
        assert empty_manager.get(empty['job_id'])['status'] == 'succeeded'
        assert empty_manager.get(empty['job_id'])['total'] == 0
    asyncio.run(scenario())


def test_concurrent_admission_only_runs_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    async def scenario():
        manager = RefreshJobManager(tmp_path)
        gate = threading.Event()
        calls = []
        def work(progress):
            calls.append(1)
            gate.wait(3)
            progress('000090', True)
        with ThreadPoolExecutor(max_workers=8) as clients:
            jobs = list(clients.map(lambda _: manager.submit('m120', ['000090'], work), range(16)))
        assert len({j['job_id'] for j in jobs}) == 1
        assert sum(not j['reused'] for j in jobs) == 1
        gate.set()
        await manager.close(timeout=2)
        assert calls == [1]
    asyncio.run(scenario())


def test_restart_interruption_and_write_failure(tmp_path):
    async def scenario():
        manager = RefreshJobManager(tmp_path)
        gate = threading.Event()
        job = manager.submit('m120', ['000090'], lambda progress: gate.wait(2))
        await manager.close(timeout=0)
        restored = RefreshJobManager(tmp_path).get(job['job_id'])
        assert restored['status'] == 'interrupted'
        assert restored['retry_codes'] == ['000090']
        assert manager.submit('m120', [], lambda p: None) is None
        gate.set()
        await manager.close(timeout=2)
        other = RefreshJobManager(tmp_path)
        def fail(progress):
            progress('000090', True)
            raise OSError('disk full')
        failed = other.submit('financial', ['000090'], fail)
        await other.close(timeout=2)
        assert other.get(failed['job_id'])['status'] == 'failed'
        assert 'disk full' in other.get(failed['job_id'])['error']
        assert other.get(failed['job_id'])['retry_codes'] == ['000090']
    asyncio.run(scenario())
