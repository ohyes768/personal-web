"""Offline tests for rental snapshot storage: publish semantics, atomic pointer
swap, corruption tolerance and the shared publish lock."""
import json
import threading

import pytest

from src.services.rental_reference.storage import (
    ADOPTABLE_STATUSES,
    CommunityBatch,
    RentalPublishLock,
    load_current,
    publish_run,
)

CAPTURED = '2026-10-12T00:00:00+00:00'
OLD_CAPTURED = '2026-09-01T00:00:00+00:00'
SAMPLE = {'source_listing_id': '3_265860917_1', 'monthly_rent_yuan': 6400.0,
          'area_m2': 89.0, 'quality_flags': ['suspected_partition']}


def batch(cid='10001039', status='complete', samples=None, captured=CAPTURED,
          quality=None, **kwargs):
    return CommunityBatch(
        community_id=cid, source='fang', source_community_id='2010067741',
        status=status, captured_at=captured,
        samples=[{'source_listing_id': f'{cid}_1_1'}] if samples is None else samples,
        quality={'duplicate_source_ids_skipped': 0} if quality is None else quality,
        **kwargs)


@pytest.fixture()
def rentals(tmp_path):
    return tmp_path / 'rentals'


def current_pointer(rentals):
    return json.loads((rentals / 'current.json').read_text(encoding='utf-8'))


def test_publish_then_load_roundtrip(rentals):
    result = publish_run(
        rentals, [batch('10001039', samples=[SAMPLE],
                        quality={'duplicate_source_ids_skipped': 2})],
        report={'errors': [], 'truncated_seeds': []})
    assert result.published is True
    assert result.reason is None
    assert result.adopted == ('10001039',)
    assert result.published_at
    current = load_current(rentals)
    assert current['run_id'] == result.run_id
    assert current['communities']['10001039'] == {
        'community_id': '10001039', 'source': 'fang',
        'source_community_id': '2010067741', 'captured_at': CAPTURED,
        'samples': [SAMPLE], 'quality': {'duplicate_source_ids_skipped': 2},
        'origin': 'this_run', 'status': 'complete'}
    report = json.loads(
        (rentals / 'runs' / result.run_id / 'report.json').read_text(encoding='utf-8'))
    assert report == {'errors': [], 'truncated_seeds': []}


def test_pointer_swap_exposes_only_complete_versions(rentals):
    first = publish_run(rentals, [batch('10001039',
                                        samples=[{'source_listing_id': 'old'}])])
    assert load_current(rentals)['run_id'] == first.run_id
    second = publish_run(rentals, [batch('10001039',
                                         samples=[{'source_listing_id': 'new'}])])
    after = load_current(rentals)
    assert after['run_id'] == second.run_id
    assert after['run_id'] != first.run_id
    assert after['communities']['10001039']['samples'] == [{'source_listing_id': 'new'}]
    # Old batch stays on disk for rollback; no half-written temp files remain.
    assert (rentals / 'runs' / first.run_id / 'batch.json').exists()
    assert list(rentals.rglob('*.tmp')) == []


def test_all_failed_does_not_switch_pointer(rentals):
    first = publish_run(rentals, [batch()])
    pointer = (rentals / 'current.json').read_text(encoding='utf-8')
    result = publish_run(rentals, [batch('10001039', status='list_failed'),
                                   batch('20044031', status='truncated')])
    assert result.published is False
    assert result.reason == 'all_failed'
    assert (rentals / 'current.json').read_text(encoding='utf-8') == pointer
    assert load_current(rentals)['run_id'] == first.run_id


def test_partial_failure_carries_over_old_samples_and_date(rentals):
    publish_run(rentals, [batch('10001039', samples=[SAMPLE]),
                          batch('20044031', captured=OLD_CAPTURED,
                                samples=[{'source_listing_id': '9_9_9'}])])
    result = publish_run(rentals, [batch('10001039',
                                         samples=[{'source_listing_id': '3_new_1'}]),
                                   batch('20044031', status='partial_detail')])
    assert result.published
    assert result.adopted == ('10001039',)
    assert result.carried_over == ('20044031',)
    communities = load_current(rentals)['communities']
    kept = communities['20044031']
    assert kept['samples'] == [{'source_listing_id': '9_9_9'}]
    assert kept['captured_at'] == OLD_CAPTURED
    assert kept['origin'] == 'carried_over'
    assert communities['10001039']['origin'] == 'this_run'
    assert communities['10001039']['samples'] == [{'source_listing_id': '3_new_1'}]


def test_failed_community_without_history_stays_absent(rentals):
    result = publish_run(rentals, [batch('20044031'),
                                   batch('10004141', status='list_failed')])
    assert result.published
    assert result.adopted == ('20044031',)
    assert result.absent == ('10004141',)
    assert set(load_current(rentals)['communities']) == {'20044031'}


def test_empty_ok_publishes_zero_samples(rentals):
    result = publish_run(rentals, [batch('10004141', status='empty_ok', samples=[])])
    assert result.published
    assert result.adopted == ('10004141',)
    record = load_current(rentals)['communities']['10004141']
    assert record['samples'] == []
    assert record['status'] == 'empty_ok'


def test_cancelled_publish_writes_nothing(rentals):
    cancel = threading.Event()
    cancel.set()
    result = publish_run(rentals, [batch()], cancel_event=cancel)
    assert result.published is False
    assert result.reason == 'cancelled'
    assert load_current(rentals) is None
    assert not (rentals / 'runs').exists()


def test_corrupt_pointer_is_tolerated(rentals):
    rentals.mkdir(parents=True)
    (rentals / 'current.json').write_text('{not json', encoding='utf-8')
    assert load_current(rentals) is None
    (rentals / 'current.json').write_text(
        json.dumps({'version': 1, 'run_id': 'no-such-run'}), encoding='utf-8')
    assert load_current(rentals) is None
    (rentals / 'current.json').write_text(
        json.dumps({'version': 2, 'run_id': 'x'}), encoding='utf-8')
    assert load_current(rentals) is None


def test_publish_treats_corrupt_previous_as_no_history(rentals):
    rentals.mkdir(parents=True)
    (rentals / 'current.json').write_text('broken', encoding='utf-8')
    result = publish_run(rentals, [batch('20044031'),
                                   batch('10004141', status='truncated')])
    assert result.published
    assert result.absent == ('10004141',)
    assert set(load_current(rentals)['communities']) == {'20044031'}


def test_single_corrupt_community_degrades(rentals):
    publish_run(rentals, [batch('10001039'), batch('20044031')])
    batch_path = rentals / 'runs' / current_pointer(rentals)['run_id'] / 'batch.json'
    data = json.loads(batch_path.read_text(encoding='utf-8'))
    data['communities']['10001039']['samples'] = 'broken'
    batch_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    current = load_current(rentals)
    assert '10001039' not in current['communities']
    assert current['degraded']['10001039'] == 'samples is not a list'
    assert '20044031' in current['communities']


def test_missing_captured_at_degrades(rentals):
    publish_run(rentals, [batch('10001039')])
    batch_path = rentals / 'runs' / current_pointer(rentals)['run_id'] / 'batch.json'
    data = json.loads(batch_path.read_text(encoding='utf-8'))
    data['communities']['10001039']['captured_at'] = None
    batch_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    current = load_current(rentals)
    assert current['communities'] == {}
    assert current['degraded'] == {'10001039': 'missing captured_at'}


def test_unreadable_batch_returns_none(rentals):
    publish_run(rentals, [batch()])
    batch_path = rentals / 'runs' / current_pointer(rentals)['run_id'] / 'batch.json'
    batch_path.write_text('garbage', encoding='utf-8')
    assert load_current(rentals) is None


def test_publish_lock_is_exclusive(rentals):
    with RentalPublishLock(rentals / 'rental_publish'):
        with pytest.raises(BlockingIOError):
            with RentalPublishLock(rentals / 'rental_publish'):
                pass


def test_publish_run_honors_shared_lock(rentals):
    with RentalPublishLock(rentals / 'rental_publish'):
        with pytest.raises(BlockingIOError):
            publish_run(rentals, [batch()])


def test_validation_and_lock_contract(rentals):
    assert ADOPTABLE_STATUSES == frozenset({'complete', 'empty_ok'})
    with pytest.raises(ValueError):
        publish_run(rentals, [])
    with pytest.raises(ValueError):
        publish_run(rentals, [batch(status='mystery')])
    with pytest.raises(ValueError):
        publish_run(rentals, [batch('10001039'), batch('10001039')])
    with pytest.raises(ValueError):
        publish_run(rentals, [batch()], run_id='../escape')
