"""Probe workflow: the system finds the homepage, the user only picks one."""
import sqlite3
import time

import pytest

from src.services.community_registry import CommunityRegistry
from src.services.rental_reference import probe
from src.services.rental_reference.probe import (
    ProbeAlreadyRunning, ProbeConflict, ProbeInvalid, ProbeService)

TOTAL_ID = '6581009489657331972'
PHASE_ID = '6598511715770433795'
SEED = '7406856173871235098'


def setup(tmp_path, name='测试花园', address='测试路1号'):
    registry = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    registry.create(name, district='滨江', address=address, community_id='c1',
                    longitude=120.188369, latitude=30.203001, coordinate_system='gcj02')
    record = registry.ingest(dict(source='tmsf', source_id='c1', name=name, district='滨江',
                                  address=address, property_type='住宅',
                                  market_state='second_hand', listing_count=3))
    registry.associate(record['id'], 'c1')
    return registry


class FakeDiscovery:
    """Stands in for the platform: search names, homepage facts, listing owners."""

    def __init__(self, *, search=None, homepages=None, owners=None, lists=None):
        self.request_count = 0
        self.calls = []
        self._search = search or {}
        self._homepages = homepages or {}
        self._owners = owners or {}
        self._lists = lists or {}

    def search(self, name, channel):
        self.request_count += 1
        self.calls.append(('search', name, channel))
        found = self._search.get((name, channel), self._search.get(name, {}))
        return {nid: {'name': platform_name, 'seeds': []} for nid, platform_name in found.items()}

    def community_info(self, neighborhood_id):
        self.request_count += 1
        self.calls.append(('community_info', neighborhood_id))
        facts = self._homepages[neighborhood_id]
        return {**{k: v for k, v in facts.items() if k not in {'seeds', 'rent_total'}},
                'city_id': 1853, 'district': facts.get('district', '滨江')}

    def rental_entry(self, neighborhood_id):
        self.request_count += 1
        self.calls.append(('rental_entry', neighborhood_id))
        facts = self._homepages[neighborhood_id]
        return dict(neighborhood_id=neighborhood_id, seeds=facts['seeds'],
                    rent_total=facts['rent_total'], rent_has_more=bool(facts['seeds']))

    def listing_owner(self, seed):
        self.request_count += 1
        self.calls.append(('listing', seed))
        return self._owners.get(seed)

    def listing_owner_from_list(self, seed, neighborhood_id):
        self.request_count += 1
        self.calls.append(('list', seed))
        return self._lists.get(seed) == neighborhood_id


def homepage(neighborhood_id=TOTAL_ID, name='测试花园', address='测试路1号', seeds=(SEED,), total=31):
    return {'neighborhood_id': neighborhood_id, 'name': name, 'address': address,
            'longitude': 120.188369, 'latitude': 30.203001, 'coordinate_system': 'gcj02',
            'rent_total': total, 'seeds': list(seeds)}


def service(registry, fake, tmp_path):
    return ProbeService(registry, directory=tmp_path / 'rentals', delay=0,
                        discovery_factory=lambda **kwargs: fake)


def run(service, community_id='c1'):
    service.start(community_id)
    service._thread.join(5)
    return service.status(community_id)


def test_identity_search_uses_only_second_hand_and_neighborhood(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery()
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_NO_HOMEPAGE
    assert [call for call in fake.calls if call[0] == 'search'] == [
        ('search', '测试花园', 'second_hand'),
        ('search', '测试花园', 'neighborhood'),
    ]


def test_single_strong_candidate_binds_without_asking(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园'}},
        homepages={TOTAL_ID: homepage()},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_BOUND
    sources = [s for s in registry.sources() if s['source'] == 'xingfuli']
    assert len(sources) == 1
    assert sources[0]['status'] == 'matched'
    assert sources[0]['community_id'] == 'c1'
    assert sources[0]['source_id'] == TOTAL_ID
    assert sources[0]['seed_listing_id'] == SEED


@pytest.mark.parametrize('automatic', [False, True])
@pytest.mark.parametrize('position', [
    {'longitude': None, 'latitude': None},
    {'coordinate_system': 'wgs84'},
])
def test_unique_exact_name_binds_without_matching_place(tmp_path, automatic, position):
    registry = setup(tmp_path, name='湘云雅苑')
    facts = {**homepage(name='湘云雅苑', address='西兴路1190号'), **position}
    fake = FakeDiscovery(search={'湘云雅苑': {TOTAL_ID: '湘云雅苑'}},
                         homepages={TOTAL_ID: facts},
                         owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    svc.start('c1', automatic=automatic)
    svc._thread.join(5)
    state = svc.status('c1')
    assert state['stage'] == probe.STAGE_BOUND
    source = next(s for s in registry.sources() if s['source'] == 'xingfuli')
    assert source['community_id'] == 'c1'
    assert '完整名称一致' in source['evidence']
    assert '地址一致' not in source['evidence']
    assert '位置接近（100米内）' not in source['evidence']


@pytest.mark.parametrize('case', ['multiple', 'incomplete', 'far', 'partial'])
def test_name_only_binding_still_requires_complete_unique_identity(tmp_path, case):
    registry = setup(tmp_path)
    facts = {**homepage(address='其他路1号'), 'longitude': None, 'latitude': None}
    search = {TOTAL_ID: '测试花园'}
    pages = {TOTAL_ID: facts}
    if case == 'multiple':
        other = '6581009489657331973'
        search[other] = '测试花园'
        pages[other] = {**facts, 'neighborhood_id': other}
    elif case == 'far':
        facts.update(longitude=120.30, latitude=30.30)
    elif case == 'partial':
        facts['name'] = search[TOTAL_ID] = '测试花园小区'
    fake = FakeDiscovery(search={'测试花园': search}, homepages=pages,
                         owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    if case == 'incomplete':
        fake.search_complete = False
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_NEEDS_SELECTION
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())
    assert not any(call[0] == 'rental_entry' for call in fake.calls)


def test_restored_name_only_candidate_is_rechecked_before_binding(tmp_path):
    registry = setup(tmp_path)
    facts = {**homepage(address='其他路1号', seeds=()), 'longitude': None, 'latitude': None}
    first = FakeDiscovery(search={'测试花园': {TOTAL_ID: '测试花园'}},
                          homepages={TOTAL_ID: facts})
    assert run(service(registry, first, tmp_path))['stage'] == probe.STAGE_NO_ENTRY
    second = FakeDiscovery(homepages={TOTAL_ID: {**facts, 'seeds': [SEED]}},
                           owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    assert run(service(registry, second, tmp_path))['stage'] == probe.STAGE_BOUND
    assert ('community_info', TOTAL_ID) in second.calls


def test_ambiguous_candidates_ask_the_user_to_choose(tmp_path):
    registry = setup(tmp_path)
    other = '6581009489657331973'
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园', other: '测试花园'}},
        homepages={TOTAL_ID: homepage(), other: homepage(neighborhood_id=other, address='测试路2号')},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    state = run(svc)
    assert state['stage'] == probe.STAGE_NEEDS_SELECTION
    assert len(state['candidates']) == 2
    assert not any(s['source'] == 'xingfuli' and s['status'] == 'matched' for s in registry.sources())

    chosen = next(c for c in state['candidates'] if c['neighborhood_id'] == TOTAL_ID)
    svc.select('c1', chosen['candidate_id'], state['revision'])
    svc._thread.join(5)
    after = svc.status('c1')
    assert after['stage'] == probe.STAGE_BOUND
    assert [s for s in registry.sources() if s['source'] == 'xingfuli' and s['status'] == 'matched']


def test_phase_variant_cannot_be_forced(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {PHASE_ID: '测试花园(南区)'}},
        homepages={PHASE_ID: homepage(neighborhood_id=PHASE_ID, name='测试花园(南区)')},
        owners={SEED: PHASE_ID}, lists={SEED: PHASE_ID})
    svc = service(registry, fake, tmp_path)
    state = run(svc)
    assert state['stage'] == probe.STAGE_NEEDS_SELECTION
    candidate = state['candidates'][0]
    assert candidate['conflicts']
    with pytest.raises(ProbeInvalid):
        svc.select('c1', candidate['candidate_id'], state['revision'])


def test_other_district_cannot_be_forced(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园'}},
        homepages={TOTAL_ID: homepage(address='萧山区北干街道金城路')},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    state = run(svc)
    assert state['stage'] == probe.STAGE_NEEDS_SELECTION
    candidate = state['candidates'][0]
    assert any('萧山区' in c for c in candidate['conflicts'])
    with pytest.raises(ProbeInvalid):
        svc.select('c1', candidate['candidate_id'], state['revision'])


def test_no_homepage_and_no_entry_are_different_reasons(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(search={}, homepages={})
    assert run(service(registry, fake, tmp_path))['stage'] == probe.STAGE_NO_HOMEPAGE

    registry2 = setup(tmp_path / 'b')
    fake2 = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园'}},
        homepages={TOTAL_ID: homepage(seeds=(), total=0)})
    assert run(service(registry2, fake2, tmp_path / 'b'))['stage'] == probe.STAGE_NO_ENTRY


def test_listing_of_another_community_is_not_an_entry(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园'}},
        homepages={TOTAL_ID: homepage()},
        owners={SEED: '6581009489657331973'}, lists={SEED: TOTAL_ID})
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_NO_ENTRY
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())


def test_stale_revision_is_rejected(tmp_path):
    registry = setup(tmp_path)
    other = '6581009489657331973'
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园', other: '测试花园'}},
        homepages={TOTAL_ID: homepage(), other: homepage(neighborhood_id=other)},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    state = run(svc)
    assert state['stage'] == probe.STAGE_NEEDS_SELECTION
    candidate = state['candidates'][0]
    with pytest.raises(ProbeConflict):
        svc.select('c1', candidate['candidate_id'], state['revision'] + 5)


def test_unknown_candidate_is_rejected(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(search={}, homepages={})
    svc = service(registry, fake, tmp_path)
    run(svc)
    with pytest.raises(ProbeConflict):
        svc.select('c1', 'second_hand:999', 1)


def test_selection_survives_a_cancelled_probe(tmp_path):
    registry = setup(tmp_path)
    other = '6581009489657331973'
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园', other: '测试花园'}},
        homepages={TOTAL_ID: homepage(), other: homepage(neighborhood_id=other)},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    state = run(svc)
    chosen = state['candidates'][0]
    svc.select('c1', chosen['candidate_id'], state['revision'])
    svc._thread.join(5)
    stored = probe.read_state(registry, 'c1')
    assert stored.get('selected_page', {}).get('neighborhood_id') == chosen['neighborhood_id']


def test_a_community_with_a_source_is_not_probed_again(tmp_path):
    registry = setup(tmp_path)
    registry.ingest(dict(source='fang', source_id='f1', name='测试花园', district='滨江',
                         address='测试路1号'))
    fake = FakeDiscovery(search={}, homepages={})
    svc = service(registry, fake, tmp_path)
    with pytest.raises((ProbeInvalid, ValueError)):
        svc.start('c1')


def test_a_running_probe_refuses_a_second_job(tmp_path):
    """Two background jobs would write the same state."""
    registry = setup(tmp_path)
    other = '6581009489657331973'
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园', other: '测试花园'}},
        homepages={TOTAL_ID: homepage(), other: homepage(neighborhood_id=other)},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    state = run(svc)
    candidate = state['candidates'][0]
    # The search is finished, but a second job must not start while another
    # one is still running; the guard is what keeps the state single-writer.
    svc._thread = _RunningThread()
    try:
        with pytest.raises(ProbeAlreadyRunning):
            svc.select('c1', candidate['candidate_id'], state['revision'])
        with pytest.raises(ProbeAlreadyRunning):
            svc.retry('c1')
    finally:
        svc._thread = None


class _RunningThread:
    """A thread stand-in that never ends, to hold the probe slot."""

    def is_alive(self):
        return True

    def join(self, timeout=None):
        return None


def test_a_cooling_platform_reports_the_cooldown(tmp_path):
    registry = setup(tmp_path)

    class Cooling(FakeDiscovery):
        def search(self, name, channel):
            raise ValueError('幸福里来源冷却中，暂停请求')

    fake = Cooling(search={}, homepages={})
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_COOLING


def test_an_unlinked_community_can_be_probed_again(tmp_path):
    """An explicit probe is the re-processing the user asked for."""
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园'}},
        homepages={TOTAL_ID: homepage()},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = service(registry, fake, tmp_path)
    state = run(svc)
    assert state['stage'] == probe.STAGE_BOUND
    # The human removed the source again; the probe may bind it once more.
    source = next(s for s in registry.sources() if s['source'] == 'xingfuli')
    registry.unlink(source['id'], 'c1')
    fake2 = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园'}},
        homepages={TOTAL_ID: homepage()},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc2 = service(registry, fake2, tmp_path)
    assert run(svc2)['stage'] == probe.STAGE_BOUND
    assert [s for s in registry.sources()
            if s['source'] == 'xingfuli' and s['status'] == 'matched']


# --- API surface ---------------------------------------------------------

def api_client(registry, fake, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import rental_routes, rental_source_routes
    svc = ProbeService(registry, directory=tmp_path / 'rentals', delay=0,
                       discovery_factory=lambda **kwargs: fake)
    monkeypatch.setattr(rental_routes, '_probe_service', svc)
    monkeypatch.setattr(rental_routes, '_mappings_path', tmp_path / 'rental_community_mappings.json')
    monkeypatch.setattr(rental_source_routes, 'load_communities',
                        lambda: [{'community_id': 'c1', 'community_name': '测试花园', 'district': '滨江'}])
    app = FastAPI()
    app.include_router(rental_source_routes.router)
    return TestClient(app), svc


def test_probe_api_starts_reads_and_rejects_a_stale_choice(tmp_path, monkeypatch):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: '测试花园', '6581009489657331973': '测试花园'}},
        homepages={TOTAL_ID: homepage(), '6581009489657331973': homepage(neighborhood_id='6581009489657331973')},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    client, svc = api_client(registry, fake, tmp_path, monkeypatch)
    assert client.get('/communities/c1/rental-source/probe').json()['data']['stage'] == 'idle'
    started = client.post('/communities/c1/rental-source/probe')
    assert started.status_code == 200
    svc._thread.join(5)
    state = client.get('/communities/c1/rental-source/probe').json()['data']
    assert state['stage'] == 'needs_homepage_selection'
    candidate = state['candidates'][0]
    stale = client.post('/communities/c1/rental-source/probe/select',
                         json={'candidate_id': candidate['candidate_id'], 'revision': state['revision'] + 3})
    assert stale.status_code == 409
    good = client.post('/communities/c1/rental-source/probe/select',
                       json={'candidate_id': candidate['candidate_id'], 'revision': state['revision']})
    assert good.status_code == 200
    svc._thread.join(5)
    assert client.get('/communities/c1/rental-source/probe').json()['data']['stage'] == 'bound_pending_collection'


def test_probe_api_refuses_a_conflicting_candidate(tmp_path, monkeypatch):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {PHASE_ID: '测试花园(南区)'}},
        homepages={PHASE_ID: homepage(neighborhood_id=PHASE_ID, name='测试花园(南区)')},
        owners={SEED: PHASE_ID}, lists={SEED: PHASE_ID})
    client, svc = api_client(registry, fake, tmp_path, monkeypatch)
    client.post('/communities/c1/rental-source/probe')
    svc._thread.join(5)
    state = client.get('/communities/c1/rental-source/probe').json()['data']
    candidate = state['candidates'][0]
    refused = client.post('/communities/c1/rental-source/probe/select',
                           json={'candidate_id': candidate['candidate_id'], 'revision': state['revision']})
    assert refused.status_code == 422


def test_probe_api_reports_a_missing_job_on_cancel(tmp_path, monkeypatch):
    registry = setup(tmp_path)
    fake = FakeDiscovery(search={}, homepages={})
    client, _ = api_client(registry, fake, tmp_path, monkeypatch)
    assert client.post('/communities/c1/rental-source/probe/cancel').status_code == 409
    assert client.post('/communities/c1/rental-source/probe').status_code == 200


# --- 只读状态读取：探查任务持写锁时 GET 不得排队或失败 --------------------
# 线上回归：探查运行期间 write_state 频繁持 SQLite 写锁，而 db() 每个连接都
# BEGIN IMMEDIATE，GET probe 轮询排队甚至 database is locked（503）。

def test_read_state_avoids_writer_lock(tmp_path):
    registry = setup(tmp_path)
    probe.write_state(registry, 'c1', stage=probe.STAGE_SEARCHING)
    holder = sqlite3.connect(registry.path, timeout=15)
    holder.execute('BEGIN IMMEDIATE')
    try:
        started = time.perf_counter()
        state = probe.read_state(registry, 'c1')
        elapsed = time.perf_counter() - started
    finally:
        holder.rollback()
        holder.close()
    assert state['stage'] == probe.STAGE_SEARCHING
    assert elapsed < 0.2, f'状态读取被写锁阻塞 {elapsed:.2f}s'


def test_community_exists_checks_identity_not_snapshot(tmp_path):
    registry = setup(tmp_path)
    assert registry.community_exists('c1')
    assert not registry.community_exists('missing')
    with registry.db() as db:
        db.execute("UPDATE communities SET deleted=1 WHERE id='c1'")
    assert not registry.community_exists('c1'), '已删除小区不应视为存在'
    with registry.db() as db:
        db.execute("UPDATE communities SET deleted=0, merged_to='other' WHERE id='c1'")
    assert not registry.community_exists('c1'), '已合并小区不应视为存在'


def test_probe_get_stays_readable_while_writer_lock_is_held(tmp_path, monkeypatch):
    registry = setup(tmp_path)
    fake = FakeDiscovery(search={}, homepages={})
    client, _ = api_client(registry, fake, tmp_path, monkeypatch)
    holder = sqlite3.connect(registry.path, timeout=15)
    holder.execute('BEGIN IMMEDIATE')
    try:
        response = client.get('/communities/c1/rental-source/probe')
    finally:
        holder.rollback()
        holder.close()
    assert response.status_code == 200
    assert response.json()['data']['stage'] == 'idle'
