"""Offline tests for the rental refresh background service.

Fake Xingfuli clients only; the crawl delay is zero so cancellation latency
comes from event waits, never sleeps. Job-state assertions read the persisted
job file to prove the state machine, not just the in-memory view.

Fang is retired: the ledger is the only source of truth, and a legacy Fang
mapping file is never a crawl source.
"""
import json
import threading
import time

import pytest

from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION
from src.services.rental_reference.crawl_types import RentalCrawlCancelled, SeedRunResult
from src.services.rental_reference.refresh import (
    JOB_FILE_NAME,
    NoVerifiedMappings,
    RefreshAlreadyRunning,
    RefreshNotRunning,
    RentalRefreshService,
    load_verified_mappings,
)
from src.services.rental_reference.storage import (
    CommunityBatch,
    RentalPublishLock,
    load_current,
    publish_run,
)

MAPPINGS_NAME = 'rental_community_mappings.json'
SEED_LISTING = '7502229388495274018'


def registry(tmp_path, count=2):
    """An admitted 滨江 community ledger with `count` residential communities."""
    reg = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    for index in range(count):
        cid = f'c{index + 1}'
        name = f'花园{index + 1}'
        community = reg.create(name, district='滨江', address=f'测试路{index + 1}号', community_id=cid)
        fact = reg.ingest(dict(source='tmsf', source_id=f't{index + 1}', name=name, district='滨江',
                               address=f'测试路{index + 1}号', property_type='住宅', listing_count=3,
                               market_state='second_hand'))
        reg.associate(fact['id'], cid)
    with reg.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    return reg


def source(reg, cid, kind='xingfuli', sid='123'):
    # The seed listing is per community: two communities must not share a seed.
    row = reg.ingest(dict(source=kind, source_id=sid, name='花园1', district='滨江',
                          address='测试路1号', seed_listing_id=sid,
                          auto_association_disabled=True,
                          source_url='https://m.xflapp.com/zufang/neighbor-house-list/'
                                     f'hz-{sid}.html'))
    if kind == 'fang':
        # Retired Fang associations only exist as historical ledger rows.
        with reg.db() as db:
            db.execute("UPDATE sources SET cid=?,status='matched',method='manual' WHERE id=?",
                       (cid, row['id']))
    else:
        reg.associate(row['id'], cid)
    return row


def legacy_mapping_file(tmp_path, entries=None):
    path = tmp_path / MAPPINGS_NAME
    if entries is None:
        entries = [
            {'source': 'fang', 'source_community_id': '2010067741',
             'community_id': '10001039', 'status': 'verified'},
        ]
    path.write_text(json.dumps({'version': 1, 'mappings': entries},
                               ensure_ascii=False), encoding='utf-8')
    return path


class FakeClient:
    """XingfuliClient stand-in: per source_id outcome, optional gate to hold a crawl.

    The gate only blocks the crawl call and the wait is bounded by the client
    timeout, mimicking a real in-flight request that eventually returns so a
    cancel can be observed.
    """

    def __init__(self, results=None, gate=None, timeout=None, gate_sources=None):
        self.results = results or {}
        self.gate = gate
        self.timeout = timeout
        self.gate_sources = gate_sources
        self.request_count = 0
        self.cooldown_until = None
        self.closed = False
        self.entered = threading.Event()

    def crawl(self, source_id, seed_listing_id, *, cancel_event=None, **kwargs):
        from src.services.xingfuli_rentals import list_url
        self.request_count += 1
        self.entered.set()
        seed = list_url(seed_listing_id)
        if self.gate is not None and (self.gate_sources is None or source_id in self.gate_sources):
            # A real in-flight request outlives the gate and eventually returns;
            # the timeout bounds it instead of killing the worker.
            self.gate.wait(self.timeout if self.timeout is not None else 5)
        if cancel_event is not None and cancel_event.is_set():
            raise RentalCrawlCancelled([], None)
        value = self.results.get(source_id)
        if isinstance(value, Exception):
            raise value
        if value is None:
            return SeedRunResult(seed=seed, status='empty_ok', pages_fetched=1)
        return SeedRunResult(seed=seed, **value)

    def close(self):
        self.closed = True


def make_service(tmp_path, results=None, gate=None, client_timeout=None, gate_sources=None, **kwargs):
    clients = []

    def factory(**_client_kwargs):
        client = FakeClient(results, gate, client_timeout, gate_sources)
        clients.append(client)
        return client

    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / MAPPINGS_NAME,
                                   xingfuli_factory=factory, delay=0,
                                   reuse_hours=kwargs.pop('reuse_hours', 0), **kwargs)
    return service, clients


def read_job_file(service):
    # The worker replaces the job file atomically; on Windows the replacement
    # can briefly lock the path, so a read retries instead of failing.
    path = service.rentals_dir / JOB_FILE_NAME
    for _ in range(100):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except PermissionError:
            time.sleep(0.01)
    raise AssertionError('job file stayed locked')


def wait_until(predicate, timeout=15.0):
    # The worker thread starts in the background; a loaded machine needs more
    # than a couple of seconds to publish its first per-seed job file.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_recent_snapshot_reused_without_network_or_new_publish(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'c1', sid='101')
    source(reg, 'c2', sid='102')
    service, _ = make_service(tmp_path, reuse_hours=6)
    service.start()
    assert wait_until(lambda: not service.status()['running'])
    first = load_current(service.rentals_dir)
    second, clients = make_service(tmp_path, {}, reuse_hours=6)
    second.start()
    assert wait_until(lambda: not second.status()['running'])
    job = second.status()
    assert job['reused_communities'] == 2
    assert job['success_count'] == 0 and job['failed_count'] == 0
    assert job['result']['published'] is False
    assert job['last_success_at'] == service.status()['last_success_at']
    assert load_current(service.rentals_dir) == first
    assert not clients or not clients[0].entered.is_set()


def test_mixed_snapshot_reuse_preserves_old_time_and_source(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'c1', sid='101')
    source(reg, 'c2', sid='102')
    service, _ = make_service(tmp_path, reuse_hours=6)
    service.start()
    assert wait_until(lambda: not service.status()['running'])
    previous = load_current(service.rentals_dir)
    batch_path = service.rentals_dir / 'runs' / previous['run_id'] / 'batch.json'
    batch = json.loads(batch_path.read_text(encoding='utf-8'))
    batch['communities']['c2']['captured_at'] = '2020-01-01T00:00:00+00:00'
    batch_path.write_text(json.dumps(batch), encoding='utf-8')
    second, _ = make_service(tmp_path, reuse_hours=6)
    second.start()
    assert wait_until(lambda: not second.status()['running'])
    job = second.status()
    assert job['reused_communities'] == 1 and job['success_count'] == 1
    current = load_current(second.rentals_dir)
    assert len(current['communities']) == 2
    assert current['communities']['c1']['captured_at'] == previous['communities']['c1']['captured_at']


def test_failed_rebound_source_does_not_carry_old_source_samples(tmp_path):
    rentals = tmp_path / 'rentals'
    publish_run(rentals, [CommunityBatch('c1', 'xingfuli', 'old', 'complete', '2020-01-01T00:00:00+00:00')])
    result = publish_run(rentals, [
        CommunityBatch('c1', 'xingfuli', 'new', 'list_failed', '2026-01-01T00:00:00+00:00'),
        CommunityBatch('c2', 'xingfuli', 'other', 'empty_ok', '2026-01-01T00:00:00+00:00')])
    assert result.absent == ('c1',) and not result.carried_over
    assert set(load_current(rentals)['communities']) == {'c2'}


def test_start_runs_job_to_done_and_persists_job_file(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'c1', sid='101')
    source(reg, 'c2', sid='102')
    service, clients = make_service(tmp_path)
    snapshot = service.start()
    assert snapshot['running'] is True
    assert snapshot['phase'] == 'crawling'
    assert snapshot['total_communities'] == 2
    assert snapshot['job_id']
    assert wait_until(lambda: service.status()['phase'] == 'done')
    job = read_job_file(service)
    assert job['running'] is False
    assert job['success_count'] == 2 and job['failed_count'] == 0
    assert job['finished_at'] and job['last_success_at']
    assert job['result']['published'] is True
    assert sorted(job['result']['adopted']) == ['c1', 'c2']
    current = load_current(service.rentals_dir)
    assert set(current['communities']) == {'c1', 'c2'}
    assert current['communities']['c2']['samples'] == []
    assert clients[0].closed is True


def test_second_start_conflicts_while_job_running(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')
    gate = threading.Event()
    service, _ = make_service(tmp_path, gate=gate)
    service.start()
    with pytest.raises(RefreshAlreadyRunning):
        service.start()
    assert service.status()['running'] is True
    gate.set()
    assert service.shutdown(timeout=5) is True


def test_start_without_verified_mappings_is_rejected(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1', kind='fang')
    service, _ = make_service(tmp_path)
    with pytest.raises(NoVerifiedMappings):
        service.start()
    assert service.status()['phase'] == 'idle'


def test_legacy_fang_mapping_file_is_not_a_crawl_source(tmp_path):
    """旧房天下映射文件保留在磁盘，但不再是采集来源。"""
    legacy_mapping_file(tmp_path)
    service, _ = make_service(tmp_path)
    with pytest.raises(NoVerifiedMappings):
        service.start()
    assert load_verified_mappings(tmp_path / MAPPINGS_NAME) == []


def test_unlinked_community_is_not_crawled(tmp_path):
    """来源被解除后没有采集计划，也不会发任何上游请求。"""
    reg = registry(tmp_path, count=1)
    linked = source(reg, 'c1')
    service, clients = make_service(tmp_path)
    reg.unlink(linked['id'])
    with pytest.raises(NoVerifiedMappings):
        service.start()
    assert not clients or not clients[0].entered.is_set()


def test_cancel_stops_job_and_never_publishes(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'c1', sid='101')
    source(reg, 'c2', sid='102')
    gate = threading.Event()
    service, _ = make_service(tmp_path, gate=gate, gate_sources={'102'})
    service.start()
    assert wait_until(lambda: service.status()['processed_communities'] == 1)
    snapshot = service.cancel()
    assert snapshot['phase'] == 'cancelling'
    gate.set()
    assert wait_until(lambda: service.status()['phase'] == 'cancelled')
    job = read_job_file(service)
    assert job['running'] is False
    assert job['processed_communities'] == 1
    assert job['result'] == {'published': False, 'reason': 'cancelled',
                             'completed_communities': 0}
    assert not (service.rentals_dir / 'current.json').exists()
    assert not (service.rentals_dir / 'runs').exists()


def test_cancel_without_active_job_conflicts(tmp_path):
    service, _ = make_service(tmp_path)
    with pytest.raises(RefreshNotRunning):
        service.cancel()


def test_all_failed_keeps_pointer_and_last_success(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')
    service, _ = make_service(tmp_path)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'done')
    first_run = service.status()['result']['run_id']
    first_success = service.status()['last_success_at']

    broken, _ = make_service(tmp_path, {'123': {'status': 'list_failed',
                                                'errors': [{'stage': 'list', 'url': 'u', 'error': '登录'}]}})
    broken.start()
    assert wait_until(lambda: broken.status()['phase'] == 'failed')
    job = read_job_file(broken)
    assert job['failed_count'] == 1
    assert job['result']['published'] is False
    assert job['result']['reason'] == 'all_failed'
    assert job['last_success_at'] == first_success
    pointer = json.loads((service.rentals_dir / 'current.json').read_text(encoding='utf-8'))
    assert pointer['run_id'] == first_run


def test_partial_success_publishes_mixed_result(tmp_path):
    # Community B has previous published samples; this run fails only B.
    rentals = tmp_path / 'rentals'
    publish_run(rentals, [CommunityBatch(
        community_id='c2', source='xingfuli',
        source_community_id='102', status='complete',
        captured_at='2026-09-01T00:00:00+00:00',
        samples=[{'source_listing_id': '9_9_9'}])])
    reg = registry(tmp_path)
    source(reg, 'c1', sid='101')
    source(reg, 'c2', sid='102')
    service, _ = make_service(tmp_path, {'102': {'status': 'list_failed',
                                                  'errors': [{'stage': 'list', 'url': 'u', 'error': '登录'}]}})
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'done')
    job = read_job_file(service)
    assert job['success_count'] == 1 and job['failed_count'] == 1
    assert job['result']['adopted'] == ['c1']
    assert job['result']['carried_over'] == ['c2']
    assert job['errors']['total'] == 1
    assert job['errors']['items'][0]['community_id'] == 'c2'
    communities = load_current(rentals)['communities']
    assert communities['c1']['origin'] == 'this_run'
    kept = communities['c2']
    assert kept['origin'] == 'carried_over'
    assert kept['captured_at'] == '2026-09-01T00:00:00+00:00'


def test_job_file_updates_per_seed_with_next_community(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'c1', sid='101')
    source(reg, 'c2', sid='102')
    gate = threading.Event()
    service, _ = make_service(tmp_path, gate=gate, gate_sources={'102'})
    service.start()
    assert wait_until(lambda: read_job_file(service)['processed_communities'] == 1)
    job = read_job_file(service)
    assert job['success_count'] == 1
    assert job['current_community_id'] == 'c2'
    gate.set()
    assert wait_until(lambda: service.status()['phase'] == 'done')


def test_restart_recovers_interrupted_job_and_keeps_lock_sidecar(tmp_path):
    rentals = tmp_path / 'rentals'
    rentals.mkdir(parents=True)
    (rentals / JOB_FILE_NAME).write_text(json.dumps(
        {'job_id': 'stale', 'running': True, 'phase': 'crawling',
         'total_communities': 3, 'processed_communities': 1,
         'current_community_id': 'c1', 'errors': {'total': 0, 'items': []}}),
        encoding='utf-8')
    lock_sidecar = rentals / 'rental_publish.lock'
    lock_sidecar.write_text('0', encoding='utf-8')
    service, _ = make_service(tmp_path)
    status = service.status()
    assert status['phase'] == 'interrupted'
    assert status['running'] is False
    assert status['processed_communities'] == 1
    persisted = read_job_file(service)
    assert persisted['phase'] == 'interrupted'
    # The sidecar file is retained and the OS lock is free: a new publish works.
    assert lock_sidecar.exists()
    result = publish_run(rentals, [CommunityBatch(
        community_id='c1', source='xingfuli',
        source_community_id='101', status='complete',
        captured_at='2026-10-12T00:00:00+00:00',
        samples=[{'source_listing_id': '3_1_1'}])])
    assert result.published is True


def test_recover_skipped_while_local_thread_alive(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')
    gate = threading.Event()
    service, _ = make_service(tmp_path, gate=gate)
    service.start()
    service._recover_interrupted_job()
    status = service.status()
    assert status['running'] is True
    assert status['phase'] == 'crawling'
    gate.set()
    assert service.shutdown(timeout=5) is True


def test_shutdown_cancels_and_joins_worker(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')
    gate = threading.Event()
    service, clients = make_service(tmp_path, gate=gate, client_timeout=1.0)
    service.start()
    # A real in-flight request outlives the cancel: the client timeout bounds
    # the crawl, then the next check observes the cancel event.
    assert service.shutdown(timeout=5) is True
    assert service.status()['phase'] == 'cancelled'
    assert not service._thread.is_alive()
    assert service.status()['running'] is False


def test_shutdown_reports_join_timeout_instead_of_blocking(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')
    gate = threading.Event()
    service, clients = make_service(tmp_path, gate=gate, client_timeout=60.0)
    service.start()
    try:
        wait_until(lambda: clients and clients[0].entered.is_set())
        assert service.shutdown(timeout=0.2) is False
        assert service._thread.is_alive()
    finally:
        gate.set()
        service._thread.join(5)


def test_publish_lock_held_by_cli_fails_job_explainably(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')
    rentals = tmp_path / 'rentals'
    service, _ = make_service(tmp_path)
    with RentalPublishLock(rentals / 'rental_publish'):
        service.start()
        assert wait_until(lambda: service.status()['phase'] == 'failed')
    job = read_job_file(service)
    assert job['result'] is None
    assert job['errors']['total'] == 1
    assert 'rental publish is already running' in job['errors']['items'][0]['error']
    assert job['errors']['items'][0]['stage'] == 'publish'
    assert not (rentals / 'current.json').exists()
    # Once the CLI releases the lock, a rerun succeeds.
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'done')


def test_worker_exception_lands_in_job_errors(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')

    def broken_factory(**_client_kwargs):
        raise RuntimeError('boom')

    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / MAPPINGS_NAME,
                                   xingfuli_factory=broken_factory, delay=0)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'failed')
    job = read_job_file(service)
    assert job['running'] is False
    assert job['errors']['total'] == 1
    assert job['errors']['items'][0]['stage'] == 'worker'
    assert 'RuntimeError: boom' in job['errors']['items'][0]['error']
    assert job['finished_at']


def test_error_cap_truncates_items_but_counts_total(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'c1', sid='101')
    source(reg, 'c2', sid='102')
    failure = {'status': 'list_failed', 'errors': [{'stage': 'list', 'url': 'u', 'error': '登录'}]}
    service, _ = make_service(tmp_path, {'101': failure, '102': failure}, max_errors_kept=1)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'failed')
    job = read_job_file(service)
    assert job['errors']['total'] == 2
    assert len(job['errors']['items']) == 1


def test_status_survives_new_instance_after_done(tmp_path):
    reg = registry(tmp_path, count=1)
    source(reg, 'c1')
    service, _ = make_service(tmp_path)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'done')
    finished = service.status()['finished_at']
    service2, _ = make_service(tmp_path)
    status = service2.status()
    assert status['phase'] == 'done'
    assert status['finished_at'] == finished
    assert status['result']['published'] is True
