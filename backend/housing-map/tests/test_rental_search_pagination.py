"""搜索分页：翻过满页首页、从断点续查，并区分请求失败/未查完/未找到。"""
import json

import pytest

from tests.test_rental_probe import FakeDiscovery, homepage, setup, service, run, TOTAL_ID, SEED
from src.services.rental_reference import probe
from src.services.rental_reference.discovery_checkpoint import PREFIX, VERSION
from src.services.rental_reference.matching import SourceMatchingService

UNRELATED = '毫不相干大厦'


class Paged(FakeDiscovery):
    """Per-offset search pages: key (name, channel, offset) -> (groups, complete)."""

    def __init__(self, *, pages=None, fail_at=(), **kwargs):
        super().__init__(**kwargs)
        self._pages = pages or {}
        self._fail_at = set(fail_at)

    def search(self, name, channel, offset=0):
        self.request_count += 1
        self.calls.append(('search', name, channel, offset))
        if (name, channel, offset) in self._fail_at:
            raise ValueError('幸福里搜索超时')
        groups, complete = self._pages.get((name, channel, offset), ({}, True))
        self.search_complete = complete
        return {nid: {'name': platform_name, 'seeds': []} for nid, platform_name in groups.items()}


def test_candidate_on_second_page_is_found_and_bound(tmp_path):
    registry = setup(tmp_path)
    fake = Paged(pages={
        ('测试花园', 'second_hand', 0): ({'a1': UNRELATED, 'a2': UNRELATED}, False),
        ('测试花园', 'second_hand', 20): ({TOTAL_ID: '测试花园'}, True),
    }, homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_BOUND
    assert ('search', '测试花园', 'second_hand', 20) in fake.calls


def test_budget_stop_defers_and_resume_advances_from_checkpoint(tmp_path):
    registry = setup(tmp_path)
    pages = {
        ('测试花园', 'second_hand', 0): ({'a1': UNRELATED}, False),
        ('测试花园', 'second_hand', 20): ({TOTAL_ID: '测试花园'}, True),
    }
    first = Paged(pages=pages, homepages={TOTAL_ID: homepage()},
                  owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, first, tmp_path)
    svc.budget = 1
    state = run(svc)
    assert state['stage'] == probe.STAGE_DEFERRED
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())

    second = Paged(pages=pages, homepages={TOTAL_ID: homepage()},
                   owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    state = run(service(registry, second, tmp_path))
    # Cached pages replay without a request; the search continues at the next
    # offset instead of repeating page one.
    assert second.calls == [('search', '测试花园', 'second_hand', 20),
                            ('community_info', TOTAL_ID),
                            ('rental_entry', TOTAL_ID), ('listing', SEED), ('list', SEED)]
    assert state['stage'] == probe.STAGE_BOUND


def test_request_failure_is_upstream_failed_and_retries_that_page(tmp_path):
    registry = setup(tmp_path)
    pages = {
        ('测试花园', 'second_hand', 0): ({'a1': UNRELATED}, False),
        ('测试花园', 'second_hand', 20): ({TOTAL_ID: '测试花园'}, True),
    }
    first = Paged(pages=pages, fail_at={('测试花园', 'second_hand', 20)},
                  homepages={TOTAL_ID: homepage()})
    state = run(service(registry, first, tmp_path))
    assert state['stage'] == probe.STAGE_FAILED
    assert '幸福里搜索超时' in state['message']

    second = Paged(pages=pages, homepages={TOTAL_ID: homepage()},
                   owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    state = run(service(registry, second, tmp_path))
    assert second.calls[0] == ('search', '测试花园', 'second_hand', 20)
    assert state['stage'] == probe.STAGE_BOUND


def test_all_pages_checked_without_candidate_is_not_found(tmp_path):
    registry = setup(tmp_path)
    fake = Paged(pages={
        ('测试花园', 'second_hand', 0): ({'a1': UNRELATED, 'a2': UNRELATED}, False),
        ('测试花园', 'second_hand', 20): ({'a3': UNRELATED}, False),
        ('测试花园', 'second_hand', 40): ({}, True),
    })
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_NO_HOMEPAGE
    assert ('search', '测试花园', 'second_hand', 40) in fake.calls


def test_incomplete_pagination_never_autobinds_a_unique_candidate(tmp_path):
    registry = setup(tmp_path)
    pages = {('测试花园', 'second_hand', 0): ({TOTAL_ID: '测试花园'}, False)}
    fake = Paged(pages=pages, homepages={TOTAL_ID: homepage()},
                 owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    svc.budget = 1
    state = run(svc)
    # Page one holds the only visible candidate, but pages may remain: an
    # unfinished search must not become a binding.
    assert state['stage'] == probe.STAGE_DEFERRED
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())
    assert not any(call[0] == 'rental_entry' for call in fake.calls)


def test_repeated_page_stops_paging_and_blocks_autobind(tmp_path):
    registry = setup(tmp_path)
    fake = Paged(pages={
        ('测试花园', 'second_hand', 0): ({TOTAL_ID: '测试花园'}, False),
        ('测试花园', 'second_hand', 20): ({TOTAL_ID: '测试花园'}, False),
    }, homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    state = run(service(registry, fake, tmp_path))
    # A page that repeats the same identities proves nothing more; paging
    # stops instead of walking into a platform that ignores the offset.
    assert ('search', '测试花园', 'second_hand', 40) not in fake.calls
    assert state['stage'] == probe.STAGE_NEEDS_SELECTION
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())


def test_old_checkpoint_version_is_discarded(tmp_path):
    registry = setup(tmp_path)
    run(service(registry, FakeDiscovery(), tmp_path))
    key = PREFIX + 'c1'
    with registry.db() as db:
        state = json.loads(db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()[0])
        state['version'] = VERSION - 1
        db.execute('UPDATE meta SET value=? WHERE key=?', (json.dumps(state), key))
    fake = FakeDiscovery()
    run(service(registry, fake, tmp_path))
    assert len(fake.calls) == 2


def test_batch_counts_incomplete_and_requeues_it(tmp_path):
    registry = setup(tmp_path)

    class Endless(FakeDiscovery):
        def search(self, name, channel, offset=0):
            self.request_count += 1
            self.calls.append(('search', name, channel, offset))
            self.search_complete = False
            return {f'id{offset}': {'name': UNRELATED, 'seeds': []}}

    fake = Endless()
    svc = SourceMatchingService(registry, directory=tmp_path / 'rentals',
                                discovery_factory=lambda **kw: fake, delay=0)
    svc._probe.budget = 2
    svc.start(mode='full')
    svc._thread.join(5)
    status = svc.status()
    # Unfinished searches are counted separately, not as failures, and the
    # next incremental run picks them up again.
    assert status['association']['incomplete'] == 1
    assert status['association']['failed'] == 0
    assert svc._targets('incremental') == ['c1']


def test_distinct_listing_pages_for_one_neighborhood_do_not_stop_search(tmp_path):
    registry = setup(tmp_path)

    class ListingPages(Paged):
        def search(self, name, channel, offset=0):
            groups = super().search(name, channel, offset)
            self.search_page_fingerprint = f'{channel}:listings:{offset}'
            return groups

    fake = ListingPages(pages={
        ('测试花园', 'second_hand', 0): ({TOTAL_ID: '测试花园'}, False),
        ('测试花园', 'second_hand', 20): ({TOTAL_ID: '测试花园'}, False),
        ('测试花园', 'second_hand', 40): ({}, True),
    }, homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    svc.budget = 2
    assert run(svc)['stage'] == probe.STAGE_DEFERRED
    resumed = service(registry, fake, tmp_path)
    assert run(resumed)['stage'] == probe.STAGE_BOUND
    assert ('search', '测试花园', 'second_hand', 40) in fake.calls


@pytest.mark.parametrize('reported_complete', [False, True])
def test_repeated_raw_listing_page_cannot_authorize_binding(tmp_path, reported_complete):
    registry = setup(tmp_path)

    class Repeated(Paged):
        def search(self, name, channel, offset=0):
            groups = super().search(name, channel, offset)
            self.search_page_fingerprint = 'same-raw-listings'
            return groups

    fake = Repeated(pages={
        ('测试花园', 'second_hand', 0): ({TOTAL_ID: '测试花园'}, False),
        ('测试花园', 'second_hand', 20): ({TOTAL_ID: '测试花园'}, reported_complete),
    }, homepages={TOTAL_ID: homepage()})
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_NEEDS_SELECTION
    assert '重复' in state['message']
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())
