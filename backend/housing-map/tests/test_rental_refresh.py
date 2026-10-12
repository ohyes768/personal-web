"""Offline tests for the rental refresh background service.

Fake fetch clients only; the crawl delay is zero so cancellation latency comes
from event waits, never sleeps. Job-state assertions read the persisted job
file to prove the state machine, not just the in-memory view.
"""
import json
import threading
import time

import pytest

from src.services.rental_reference.refresh import (
    JOB_FILE_NAME,
    MappingFileError,
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

SEED_A = 'https://zu.fang.com/hz/house-xm2010067741/'
SEED_B = 'https://zu.fang.com/hz/house-xm2011095896/'
DETAIL_1 = 'https://zu.fang.com/hz/chuzu/3_123_1.htm'
DETAIL_2 = 'https://zu.fang.com/hz/chuzu/1_456_1.htm'
DETAIL_HTML = '<title>房天下</title>费用明细 物业类型 住宅 地 址 月明路1076号 电话咨询'


def page(rows='', next_link=''):
    return ('<title>杭州租房 - 房天下</title><div class="houseList">' + rows
            + '</div>' + next_link)


def listing(listing_id='3_123_1'):
    return f'''<dl><dt><a href="/hz/chuzu/{listing_id}.htm">图片</a></dt><dd>
    <p class="title"><a href="/hz/chuzu/{listing_id}.htm">三房出租</a></p>
    <p class="font15">整租 | 3室2厅 | 89㎡ | 朝南</p>
    <p><a>滨江</a>-<a>长河</a>-<a href="/hz/house-xm2010067741/">风雅钱塘</a></p>
    <div class="moreInfo"><p><b>6,400</b> 元/月</p></div></dd></dl>'''


def next_link(url):
    return f'<a href="{url}">下一页</a>'


class FakeClient:
    """FangClient stand-in: fixed pages, optional gate to hold a request.

    The gate only blocks gate_urls (default: every URL) and the wait is
    bounded by the client timeout, mimicking a real in-flight request that
    eventually returns so a cancel can be observed on the next check.
    """

    def __init__(self, pages, gate=None, gate_urls=None, timeout=None):
        self.pages = pages
        self.gate = gate
        self.gate_urls = gate_urls
        self.timeout = timeout
        self.closed = False

    def fetch(self, url):
        if (self.gate is not None
                and (self.gate_urls is None or url in self.gate_urls)
                and not self.gate.wait(self.timeout if self.timeout is not None else 5)):
            raise AssertionError('gate wait timed out in test')
        return self.pages[url]

    def close(self):
        self.closed = True


def write_mappings(tmp_path, entries=None):
    path = tmp_path / 'rental_community_mappings.json'
    if entries is None:
        entries = [
            {'source': 'fang', 'source_community_id': '2010067741',
             'community_id': '10001039', 'status': 'verified'},
            {'source': 'fang', 'source_community_id': '2011095896',
             'community_id': '20044031', 'status': 'verified'},
        ]
    path.write_text(json.dumps({'version': 1, 'mappings': entries},
                               ensure_ascii=False), encoding='utf-8')
    return path


def make_service(tmp_path, pages, gate=None, gate_urls=None, mappings=None,
                 client_timeout=None, **kwargs):
    clients = []

    def factory(timeout):
        # client_timeout overrides the service-provided timeout from
        # construction time; setting it after start() races with the worker,
        # which may already be inside its first gate.wait.
        client = FakeClient(pages, gate, gate_urls,
                            client_timeout if client_timeout is not None else timeout)
        clients.append(client)
        return client

    mappings_path = (write_mappings(tmp_path) if mappings is None
                     else write_mappings(tmp_path, mappings))
    service = RentalRefreshService(tmp_path / 'rentals', mappings_path,
                                   fetch_factory=factory, delay=0, **kwargs)
    return service, clients


def read_job_file(service):
    return json.loads((service.rentals_dir / JOB_FILE_NAME).read_text(encoding='utf-8'))


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_start_runs_job_to_done_and_persists_job_file(tmp_path):
    pages = {SEED_A: page(listing()), SEED_B: page('', '<p>暂无房源</p>'),
             DETAIL_1: DETAIL_HTML}
    service, clients = make_service(tmp_path, pages)
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
    assert job['result']['adopted'] == ['10001039', '20044031']
    current = load_current(service.rentals_dir)
    assert set(current['communities']) == {'10001039', '20044031'}
    assert current['communities']['20044031']['samples'] == []
    assert clients[0].closed is True


def test_second_start_conflicts_while_job_running(tmp_path):
    gate = threading.Event()
    pages = {SEED_A: page(listing()), SEED_B: page(listing('1_456_1'))}
    service, _ = make_service(tmp_path, pages, gate=gate, gate_urls={SEED_A})
    service.start()
    with pytest.raises(RefreshAlreadyRunning):
        service.start()
    assert service.status()['running'] is True
    gate.set()
    assert service.shutdown(timeout=5) is True


def test_start_without_verified_mappings_is_rejected(tmp_path):
    service, _ = make_service(tmp_path, {}, mappings=[
        {'source': 'fang', 'source_community_id': '2010067741',
         'community_id': '10001039', 'status': 'pending'}])
    with pytest.raises(NoVerifiedMappings):
        service.start()
    assert service.status()['phase'] == 'idle'


def test_missing_mapping_file_is_rejected(tmp_path):
    service, _ = make_service(tmp_path, {})
    (tmp_path / 'rental_community_mappings.json').unlink()
    with pytest.raises(NoVerifiedMappings):
        service.start()


def test_corrupt_mapping_file_raises(tmp_path):
    service, _ = make_service(tmp_path, {})
    (tmp_path / 'rental_community_mappings.json').write_text('{broken', encoding='utf-8')
    with pytest.raises(MappingFileError):
        service.start()
    with pytest.raises(MappingFileError):
        load_verified_mappings(tmp_path / 'rental_community_mappings.json')


def test_duplicate_source_id_in_ledger_raises(tmp_path):
    entries = [
        {'source': 'fang', 'source_community_id': '2010067741',
         'community_id': '10001039', 'status': 'verified'},
        {'source': 'fang', 'source_community_id': '2010067741',
         'community_id': '20044031', 'status': 'verified'},
    ]
    with pytest.raises(MappingFileError):
        load_verified_mappings(write_mappings(tmp_path, entries))


def test_cancel_stops_job_and_never_publishes(tmp_path):
    gate = threading.Event()
    pages = {SEED_A: page(listing()),
             SEED_B: page(listing('1_456_1'), next_link(SEED_B + 'i32/')),
             DETAIL_1: DETAIL_HTML,
             SEED_B + 'i32/': page()}
    service, _ = make_service(tmp_path, pages, gate=gate, gate_urls={SEED_B})
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
                             'completed_communities': 1}
    assert not (service.rentals_dir / 'current.json').exists()
    assert not (service.rentals_dir / 'runs').exists()


def test_cancel_without_active_job_conflicts(tmp_path):
    service, _ = make_service(tmp_path, {})
    with pytest.raises(RefreshNotRunning):
        service.cancel()


def test_all_failed_keeps_pointer_and_last_success(tmp_path):
    pages_ok = {SEED_A: page(listing()), SEED_B: page(listing('1_456_1')),
                DETAIL_1: DETAIL_HTML, DETAIL_2: DETAIL_HTML}
    service, _ = make_service(tmp_path, pages_ok)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'done')
    first_run = service.status()['result']['run_id']
    first_success = service.status()['last_success_at']

    pages_bad = {SEED_A: '<title>登录</title>', SEED_B: '<title>登录</title>'}
    service2, _ = make_service(tmp_path, pages_bad)
    service2.start()
    assert wait_until(lambda: service2.status()['phase'] == 'failed')
    job = read_job_file(service2)
    assert job['failed_count'] == 2
    assert job['result']['published'] is False
    assert job['result']['reason'] == 'all_failed'
    assert job['last_success_at'] == first_success
    pointer = json.loads((service.rentals_dir / 'current.json').read_text(encoding='utf-8'))
    assert pointer['run_id'] == first_run


def test_partial_success_publishes_mixed_result(tmp_path):
    # Community B has previous published samples; this run fails only B.
    rentals = tmp_path / 'rentals'
    publish_run(rentals, [CommunityBatch(
        community_id='20044031', source='fang',
        source_community_id='2011095896', status='complete',
        captured_at='2026-09-01T00:00:00+00:00',
        samples=[{'source_listing_id': '9_9_9'}])])
    pages = {SEED_A: page(listing()), SEED_B: '<title>登录</title>',
             DETAIL_1: DETAIL_HTML}
    service, _ = make_service(tmp_path, pages)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'done')
    job = read_job_file(service)
    assert job['success_count'] == 1 and job['failed_count'] == 1
    assert job['result']['adopted'] == ['10001039']
    assert job['result']['carried_over'] == ['20044031']
    assert job['errors']['total'] == 1
    assert job['errors']['items'][0]['community_id'] == '20044031'
    communities = load_current(rentals)['communities']
    assert communities['10001039']['origin'] == 'this_run'
    kept = communities['20044031']
    assert kept['origin'] == 'carried_over'
    assert kept['captured_at'] == '2026-09-01T00:00:00+00:00'


def test_job_file_updates_per_seed_with_next_community(tmp_path):
    gate = threading.Event()
    pages = {SEED_A: page(listing()), SEED_B: page(listing('1_456_1')),
             DETAIL_1: DETAIL_HTML, DETAIL_2: DETAIL_HTML}
    service, _ = make_service(tmp_path, pages, gate=gate, gate_urls={SEED_B})
    service.start()
    assert wait_until(lambda: read_job_file(service)['processed_communities'] == 1)
    job = read_job_file(service)
    assert job['success_count'] == 1
    assert job['current_community_id'] == '20044031'
    gate.set()
    assert wait_until(lambda: service.status()['phase'] == 'done')


def test_restart_recovers_interrupted_job_and_keeps_lock_sidecar(tmp_path):
    rentals = tmp_path / 'rentals'
    rentals.mkdir(parents=True)
    (rentals / JOB_FILE_NAME).write_text(json.dumps(
        {'job_id': 'stale', 'running': True, 'phase': 'crawling',
         'total_communities': 3, 'processed_communities': 1,
         'current_community_id': '10004141', 'errors': {'total': 0, 'items': []}}),
        encoding='utf-8')
    lock_sidecar = rentals / 'rental_publish.lock'
    lock_sidecar.write_text('0', encoding='utf-8')
    service, _ = make_service(tmp_path, {})
    status = service.status()
    assert status['phase'] == 'interrupted'
    assert status['running'] is False
    assert status['processed_communities'] == 1
    persisted = read_job_file(service)
    assert persisted['phase'] == 'interrupted'
    # The sidecar file is retained and the OS lock is free: a new publish works.
    assert lock_sidecar.exists()
    result = publish_run(rentals, [CommunityBatch(
        community_id='10001039', source='fang',
        source_community_id='2010067741', status='complete',
        captured_at='2026-10-12T00:00:00+00:00',
        samples=[{'source_listing_id': '3_1_1'}])])
    assert result.published is True


def test_recover_skipped_while_local_thread_alive(tmp_path):
    gate = threading.Event()
    pages = {SEED_A: page(listing())}
    service, _ = make_service(tmp_path, pages, gate=gate, gate_urls={SEED_A})
    service.start()
    service._recover_interrupted_job()
    status = service.status()
    assert status['running'] is True
    assert status['phase'] == 'crawling'
    gate.set()
    assert service.shutdown(timeout=5) is True


def test_shutdown_cancels_and_joins_worker(tmp_path):
    gate = threading.Event()
    pages = {SEED_A: page(listing())}
    service, clients = make_service(tmp_path, pages, gate=gate, gate_urls={SEED_A},
                                    client_timeout=1.0)
    service.start()
    # A real in-flight request outlives the cancel: the client timeout bounds
    # the fetch, then the next request check observes the cancel event.
    assert service.shutdown(timeout=5) is True
    assert service.status()['phase'] == 'cancelled'
    assert not service._thread.is_alive()
    assert service.status()['running'] is False


def test_shutdown_reports_join_timeout_instead_of_blocking(tmp_path):
    gate = threading.Event()
    pages = {SEED_A: page(listing())}
    service, clients = make_service(tmp_path, pages, gate=gate, gate_urls={SEED_A},
                                    client_timeout=60.0)
    service.start()
    try:
        assert service.shutdown(timeout=0.2) is False
        assert service._thread.is_alive()
    finally:
        gate.set()
        service._thread.join(5)


def test_publish_lock_held_by_cli_fails_job_explainably(tmp_path):
    rentals = tmp_path / 'rentals'
    pages = {SEED_A: page(listing()), SEED_B: page(listing('1_456_1')),
             DETAIL_1: DETAIL_HTML, DETAIL_2: DETAIL_HTML}
    service, _ = make_service(tmp_path, pages)
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
    def broken_factory(timeout):
        raise RuntimeError('boom')

    service = RentalRefreshService(tmp_path / 'rentals', write_mappings(tmp_path),
                                   fetch_factory=broken_factory, delay=0)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'failed')
    job = read_job_file(service)
    assert job['running'] is False
    assert job['errors']['total'] == 1
    assert job['errors']['items'][0]['stage'] == 'worker'
    assert 'RuntimeError: boom' in job['errors']['items'][0]['error']
    assert job['finished_at']


def test_error_cap_truncates_items_but_counts_total(tmp_path):
    pages = {SEED_A: '<title>登录</title>', SEED_B: '<title>登录</title>'}
    service, _ = make_service(tmp_path, pages, max_errors_kept=1)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'failed')
    job = read_job_file(service)
    assert job['errors']['total'] == 2
    assert len(job['errors']['items']) == 1


def test_status_survives_new_instance_after_done(tmp_path):
    pages = {SEED_A: page(listing()), DETAIL_1: DETAIL_HTML}
    service, _ = make_service(tmp_path, pages)
    service.start()
    assert wait_until(lambda: service.status()['phase'] == 'done')
    finished = service.status()['finished_at']
    service2, _ = make_service(tmp_path, {})
    status = service2.status()
    assert status['phase'] == 'done'
    assert status['finished_at'] == finished
    assert status['result']['published'] is True
