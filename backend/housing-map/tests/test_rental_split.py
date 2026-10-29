"""The two web actions must never collect and discover in the same job."""
import pytest

from tests.test_rental_probe import FakeDiscovery, homepage, setup, TOTAL_ID, SEED
from tests.test_rental_providers import registry, source
from src.services.rental_reference.refresh import RentalRefreshService, NoVerifiedMappings
from src.services.rental_reference.providers import source_url
from src.services.rental_reference.storage import load_current
from src.services.fang_rentals import SeedRunResult


def forbidden(**kwargs):
    raise AssertionError('source discovery / Fang must not run during rent collection')


def test_collection_only_uses_confirmed_xingfuli_even_with_missing_neighbors(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'xingfuli')
    reg.create('无来源住宅', community_id='missing', district='滨江', address='测试路2号')
    fact = reg.ingest(dict(source='tmsf', source_id='missing', name='无来源住宅',
                           district='滨江', address='测试路2号', property_type='住宅', listing_count=3, market_state='second_hand'))
    reg.associate(fact['id'], 'missing')
    class Client:
        request_count = 1
        cooldown_until = None
        def __init__(self, **kwargs): pass
        def crawl(self, sid, seed, **kwargs):
            return SeedRunResult(seed=source_url(next(s for s in reg.sources() if s['source'] == 'xingfuli')),
                                 status='empty_ok', pages_fetched=1)
        def close(self): pass
    svc = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                               xingfuli_only=True, fetch_factory=forbidden,
                               discovery_factory=forbidden, xingfuli_factory=Client)
    svc.start()
    svc._thread.join(5)
    assert svc.status()['phase'] == 'done', svc.status()
    assert set(load_current(tmp_path / 'rentals')['communities']) == {'pilot'}


def test_collection_with_only_old_fang_source_requires_matching(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'fang')
    svc = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                               xingfuli_only=True, fetch_factory=forbidden)
    with pytest.raises(NoVerifiedMappings):
        svc.start()


def test_matching_binds_without_publishing_any_rent_samples(tmp_path):
    from src.services.rental_reference.matching import SourceMatchingService
    reg = setup(tmp_path)
    fake = FakeDiscovery(search={'测试花园': {TOTAL_ID: '测试花园'}},
                         homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals',
                                discovery_factory=lambda **kwargs: fake, delay=0)
    svc.start()
    svc._thread.join(5)
    state = svc.status()
    assert not state['running'] and state['processed'] == state['total'] == 1, state
    assert state['association']['matched'] == 1
    assert any(s['source'] == 'xingfuli' and s['status'] == 'matched' for s in reg.sources())
    assert load_current(tmp_path / 'rentals') is None
    assert not (tmp_path / 'rentals' / 'refresh_job.json').exists()


def test_matching_visits_all_missing_communities_and_preserves_human_skip(tmp_path):
    from src.services.rental_reference.matching import SourceMatchingService
    from src.services.rental_reference.association import save_review
    reg = setup(tmp_path)
    save_review(reg, reg.communities()[0], 'skipped', [])
    fake = FakeDiscovery()
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals',
                                discovery_factory=lambda **kwargs: fake, delay=0)
    svc.start()
    svc._thread.join(5)
    assert svc.status()['total'] == 0
    assert not fake.calls


def test_matching_visits_more_than_one_community_and_projects_pending_candidates(tmp_path):
    from src.services.rental_reference.matching import SourceMatchingService, source_reviews
    reg = setup(tmp_path)
    reg.create('第二花园', community_id='c2', district='滨江', address='测试路2号')
    fact = reg.ingest(dict(source='tmsf', source_id='c2', name='第二花园', district='滨江',
                           address='测试路2号', property_type='住宅', listing_count=3, market_state='second_hand'))
    reg.associate(fact['id'], 'c2')
    fake = FakeDiscovery(search={'测试花园': {TOTAL_ID: '测试花园'}},
                         homepages={TOTAL_ID: {**homepage(address='其他路'), 'longitude': 1}})
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals', discovery_factory=lambda **kw: fake)
    svc.start(); svc._thread.join(5)
    assert svc.status()['processed'] == svc.status()['total'] == 2
    assert svc.status()['association']['pending'] == 1
    assert {r['community_id']: r['reason'] for r in source_reviews(reg)} == {'c1': 'needs_selection', 'c2': 'missing'}


def test_matching_cancellation_and_restart_preserve_remaining_targets(tmp_path):
    import threading
    from src.services.rental_reference.matching import SourceMatchingService
    reg = setup(tmp_path)
    entered, release = threading.Event(), threading.Event()
    class Blocking(FakeDiscovery):
        def search(self, name, channel):
            entered.set()
            assert release.wait(5)
            return super().search(name, channel)
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals', discovery_factory=lambda **kw: Blocking())
    svc.start(); assert entered.wait(2)
    svc.cancel(); release.set(); svc._thread.join(5)
    assert svc.status()['phase'] == 'cancelled'
    assert svc.status()['remaining'] == ['c1']
    resumed = SourceMatchingService(reg, directory=tmp_path / 'rentals', discovery_factory=lambda **kw: FakeDiscovery())
    resumed.start(); resumed._thread.join(5)
    assert resumed.status()['processed'] == resumed.status()['total'] == 1
    assert resumed.status()['phase'] == 'done'


def test_matching_and_collecting_reject_other_running_work(tmp_path):
    from src.services.rental_reference.matching import SourceMatchingService
    from src.services.rental_reference.refresh import RefreshAlreadyRunning
    reg = setup(tmp_path)
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals', busy=lambda: True)
    with pytest.raises(RefreshAlreadyRunning): svc.start()
    collector = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                     xingfuli_only=True, busy=lambda: True)
    with pytest.raises(RefreshAlreadyRunning): collector.start()


def test_matching_api_and_retired_fang_endpoints(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import rental_routes, rental_source_routes
    from src.services.rental_reference.matching import SourceMatchingService
    reg = setup(tmp_path)
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals', discovery_factory=lambda **kw: FakeDiscovery())
    monkeypatch.setattr(rental_routes, '_get_matching_service', lambda: svc)
    app = FastAPI(); app.include_router(rental_source_routes.router)
    client = TestClient(app)
    assert client.get('/rentals/source-matching').json()['data']['phase'] == 'idle'
    assert not svc._thread  # GET never starts any network job.
    assert client.post('/rentals/source-matching').status_code == 202
    svc._thread.join(5)
    assert client.get('/rentals/source-matching').json()['data']['processed'] == 1
    assert client.delete('/rentals/source-matching').status_code == 409
    assert client.post('/communities/c1/rental-source/search', json={}).status_code == 410
    assert client.put('/communities/c1/rental-source', json={'source_community_id': '123'}).status_code == 410
