"""Probe workflow: the system finds the homepage, the user only picks one."""
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
