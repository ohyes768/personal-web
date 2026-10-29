"""Fewer discovery requests, durable reuse, and explicit batch scopes."""
import json
import subprocess
import sys
import textwrap

import pytest

from tests.test_rental_probe import FakeDiscovery, homepage, setup, service, run, TOTAL_ID, SEED
from src.services.rental_reference.probe import STAGE_BOUND, STAGE_NEEDS_SELECTION
from src.services.rental_reference.matching import SourceMatchingService


def strong():
    return FakeDiscovery(search={'测试花园': {TOTAL_ID: '测试花园'}},
                         homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})


@pytest.mark.parametrize('mode', ['full', 'incremental'])
def test_unlinked_amap_does_not_exclude_or_veto_rental_matching(tmp_path, mode):
    reg = setup(tmp_path)
    record = reg.ingest(dict(source='amap', source_kind='poi', source_id='old-poi',
                             name='测试花园', district='滨江', address='测试路1号'))
    reg.associate(record['id'], 'c1')
    reg.unlink(record['id'])
    fake = strong()
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals',
                                discovery_factory=lambda **kw: fake, delay=0)
    svc.start(mode=mode)
    svc._thread.join(5)
    state = svc.status()
    assert not state['running']
    assert state['processed'] == state['total'] == 1
    assert state['association']['matched'] == 1
    with reg.db() as db:
        assert db.execute('SELECT 1 FROM rejected WHERE rid=? AND cid=?',
                          (record['id'], 'c1')).fetchone()
    assert next(s for s in reg.sources() if s['id'] == record['id'])['community_id'] is None


@pytest.mark.parametrize('provider', ['fang', 'xingfuli'])
def test_unlinked_rental_source_still_excludes_batch_and_vetoes_binding(tmp_path, provider):
    from src.services.rental_reference.xingfuli_sources import protected, bind_source
    reg = setup(tmp_path)
    record = reg.ingest(dict(source=provider, source_id='12345', name='测试花园',
                             district='滨江', address='测试路1号'))
    reg.associate(record['id'], 'c1')
    reg.unlink(record['id'])
    fake = strong()
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals',
                                discovery_factory=lambda **kw: fake, delay=0)
    assert svc._targets('full') == svc._targets('incremental') == []
    assert protected(reg, 'c1')
    with pytest.raises(ValueError, match='人工已解除或拒绝'):
        bind_source(reg, reg.communities()[0], homepage(), seed=SEED,
                    method='auto', evidence=['测试'])
    assert not any(s['source'] == 'xingfuli' and s['status'] == 'matched' for s in reg.sources())


def test_complete_unique_channel_stops_search_but_verifies_both_owners(tmp_path):
    reg = setup(tmp_path)
    fake = strong()
    state = run(service(reg, fake, tmp_path))
    assert state['stage'] == STAGE_BOUND
    assert fake.calls == [('search', '测试花园', 'second_hand'), ('homepage', TOTAL_ID),
                          ('listing', SEED), ('list', SEED)]
    assert state['diagnostics']['early_stop'] is True
    assert state['diagnostics']['requests'] == 4


def test_failed_competitor_never_allows_automatic_binding(tmp_path):
    reg = setup(tmp_path)
    fake = strong()
    fake._search = {'测试花园': {TOTAL_ID: '测试花园', 'other': '测试花园'}}
    original = fake.homepage
    def read(nid):
        if nid == 'other':
            raise ValueError('temporarily unavailable')
        return original(nid)
    fake.homepage = read
    state = run(service(reg, fake, tmp_path))
    assert state['stage'] == STAGE_NEEDS_SELECTION
    assert ('search', '测试花园', 'rent') in fake.calls
    assert not any(c[0] == 'listing' for c in fake.calls)


def test_restart_reuses_successful_empty_searches_and_full_refresh_bypasses(tmp_path):
    reg = setup(tmp_path)
    first = FakeDiscovery()
    run(service(reg, first, tmp_path))
    assert len(first.calls) == 3
    second = FakeDiscovery()
    state = run(service(reg, second, tmp_path))
    assert second.calls == []
    assert state['diagnostics']['cache_hits'] == 3
    third = FakeDiscovery()
    batch = SourceMatchingService(reg, directory=tmp_path / 'rentals', discovery_factory=lambda **kw: third)
    batch.start(mode='full'); batch._thread.join(5)
    assert len(third.calls) == 3


def test_incremental_skips_finished_missing_but_full_rechecks(tmp_path):
    reg = setup(tmp_path)
    fake = FakeDiscovery()
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals', discovery_factory=lambda **kw: fake)
    svc.start(mode='full'); svc._thread.join(5)
    assert svc.status()['incremental_count'] == 0
    svc.start(mode='incremental'); svc._thread.join(5)
    assert svc.status()['total'] == 0
    assert len(fake.calls) == 3
    svc.start(mode='full'); svc._thread.join(5)
    assert len(fake.calls) == 6


def test_incremental_uses_legacy_remaining_and_retries_failures(tmp_path):
    reg = setup(tmp_path)
    directory = tmp_path / 'rentals'; directory.mkdir()
    (directory / 'source_matching_job.json').write_text(json.dumps(dict(
        running=False, phase='done', remaining=[], outcomes={'c1': 'failed'})))
    svc = SourceMatchingService(reg, directory=directory, discovery_factory=lambda **kw: FakeDiscovery())
    assert svc.status()['incremental_count'] == 1
    svc.start(mode='incremental'); svc._thread.join(5)
    assert svc.status()['processed'] == 1
    assert svc.status()['association']['failed'] == 0


def test_mode_validation(tmp_path):
    svc = SourceMatchingService(setup(tmp_path), directory=tmp_path / 'rentals')
    with pytest.raises(ValueError):
        svc.start(mode='typo')


def test_api_modes_are_validated_and_forwarded(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import rental_routes, rental_source_routes
    svc = SourceMatchingService(setup(tmp_path), directory=tmp_path / 'rentals',
                                discovery_factory=lambda **kw: FakeDiscovery())
    monkeypatch.setattr(rental_routes, '_get_matching_service', lambda: svc)
    app = FastAPI(); app.include_router(rental_source_routes.router)
    client = TestClient(app)
    assert client.post('/rentals/source-matching', json={'mode': 'bad'}).status_code == 422
    assert client.post('/rentals/source-matching', json={'mode': 'full'}).status_code == 202
    svc._thread.join(5)
    assert client.get('/rentals/source-matching').json()['data']['mode'] == 'full'
    assert client.post('/rentals/source-matching', json={'mode': 'incremental'}).status_code == 202
    svc._thread.join(5)
    assert svc.status()['total'] == 0


def test_cache_expiry_corruption_and_identity_change_force_requery(tmp_path):
    from src.services.rental_reference.discovery_checkpoint import PREFIX
    reg = setup(tmp_path)
    run(service(reg, FakeDiscovery(), tmp_path))
    key = PREFIX + 'c1'
    with reg.db() as db:
        state = json.loads(db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()[0])
        for step in state['steps'].values():
            step['expires_at'] = 0
        db.execute('UPDATE meta SET value=? WHERE key=?', (json.dumps(state), key))
    fake = FakeDiscovery(); run(service(reg, fake, tmp_path))
    assert len(fake.calls) == 3
    with reg.db() as db:
        db.execute('UPDATE meta SET value=? WHERE key=?', ('not-json', key))
    fake = FakeDiscovery(); run(service(reg, fake, tmp_path))
    assert len(fake.calls) == 3
    reg.update('c1', name='测试花园', aliases=[], address='新路1号')
    fake = FakeDiscovery(); run(service(reg, fake, tmp_path))
    assert len(fake.calls) == 3


def test_steps_survive_process_recreation_after_partial_search(tmp_path):
    from src.services.fang_rentals import RentalCrawlCancelled
    reg = setup(tmp_path)
    class Interrupted(FakeDiscovery):
        def search(self, name, channel):
            if channel == 'rent':
                raise RentalCrawlCancelled([], None)
            return super().search(name, channel)
    assert run(service(reg, Interrupted(), tmp_path))['stage'] == 'cancelled'
    fake = FakeDiscovery(); state = run(service(reg, fake, tmp_path))
    assert fake.calls == [('search', '测试花园', 'rent'), ('search', '测试花园', 'neighborhood')]
    assert state['diagnostics']['cache_hits'] == 1


def test_upstream_failures_are_not_saved_as_empty_results(tmp_path):
    reg = setup(tmp_path)
    class Broken(FakeDiscovery):
        def search(self, name, channel):
            raise ValueError('verification required')
    assert run(service(reg, Broken(), tmp_path))['stage'] == 'upstream_failed'
    fake = FakeDiscovery(); run(service(reg, fake, tmp_path))
    assert len(fake.calls) == 3


def test_restored_identity_refreshes_seeds_and_ownership(tmp_path):
    reg = setup(tmp_path)
    # No entry: a second attempt can reuse identity, but must get fresh seeds.
    first = strong(); first._homepages[TOTAL_ID] = homepage(seeds=())
    assert run(service(reg, first, tmp_path))['stage'] == 'entry_not_found'
    second = strong(); state = run(service(reg, second, tmp_path))
    assert state['stage'] == STAGE_BOUND
    assert second.calls == [('homepage', TOTAL_ID), ('listing', SEED), ('list', SEED)]


def test_budget_truncation_cannot_bind_and_applies_before_list_check(tmp_path):
    reg = setup(tmp_path)
    fake = strong()
    svc = service(reg, fake, tmp_path); svc.budget = 3
    assert run(svc)['stage'] == 'deferred'
    assert not any(call[0] == 'list' for call in fake.calls)
    assert not any(s['source'] == 'xingfuli' for s in reg.sources())


def test_early_stop_can_be_disabled_for_comparable_request_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv('HOUSING_XINGFULI_EARLY_STOP', '0')
    fake = strong()
    assert run(service(setup(tmp_path), fake, tmp_path))['stage'] == STAGE_BOUND
    assert len(fake.calls) == 6


def test_diagnostics_accumulate_across_communities(tmp_path):
    reg = setup(tmp_path)
    reg.create('第二花园', community_id='c2', district='滨江', address='测试路2号')
    fact = reg.ingest(dict(source='tmsf', source_id='c2', name='第二花园', district='滨江',
                           address='测试路2号', property_type='住宅', listing_count=3, market_state='second_hand'))
    reg.associate(fact['id'], 'c2')
    svc = SourceMatchingService(reg, directory=tmp_path / 'rentals', discovery_factory=lambda **kw: FakeDiscovery())
    svc.start(mode='full'); svc._thread.join(5)
    assert svc.status()['diagnostics']['requests'] == 6


def test_truncated_search_never_autobinds(tmp_path):
    fake = strong(); fake.search_complete = False
    assert run(service(setup(tmp_path), fake, tmp_path))['stage'] == STAGE_NEEDS_SELECTION
    assert not any(c[0] == 'listing' for c in fake.calls)


def test_damaged_cached_steps_are_requeried(tmp_path):
    from src.services.rental_reference.discovery_checkpoint import PREFIX
    reg = setup(tmp_path)
    run(service(reg, FakeDiscovery(), tmp_path))
    with reg.db() as db:
        key = PREFIX + 'c1'
        payload = json.loads(db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()[0])
        for step in payload['steps'].values():
            step['value'] = {'wrong': {}}
        db.execute('UPDATE meta SET value=? WHERE key=?', (json.dumps(payload), key))
    fake = FakeDiscovery()
    assert run(service(reg, fake, tmp_path))['stage'] == 'homepage_not_found'
    assert len(fake.calls) == 3


def test_cache_can_be_disabled(tmp_path, monkeypatch):
    reg = setup(tmp_path)
    run(service(reg, FakeDiscovery(), tmp_path))
    monkeypatch.setenv('HOUSING_XINGFULI_DISCOVERY_CACHE', '0')
    fake = FakeDiscovery(); run(service(reg, fake, tmp_path))
    assert len(fake.calls) == 3


def test_completed_http_step_survives_abrupt_process_exit(tmp_path):
    reg = setup(tmp_path)
    script = textwrap.dedent('''
        import os, sys
        from pathlib import Path
        from src.services.community_registry import CommunityRegistry
        from tests.test_rental_probe import FakeDiscovery, service, run
        class ExitAfterFirst(FakeDiscovery):
            def search(self, name, channel):
                if channel == 'rent':
                    os._exit(0)
                return super().search(name, channel)
        directory = Path(sys.argv[1])
        reg = CommunityRegistry(directory / 'community_registry.sqlite3')
        run(service(reg, ExitAfterFirst(), directory))
        raise RuntimeError('expected process exit')
    ''')
    subprocess.run([sys.executable, '-c', script, str(tmp_path)], check=True, timeout=15)
    fake = FakeDiscovery()
    state = run(service(reg, fake, tmp_path))
    assert state['diagnostics']['cache_hits'] == 1
    assert fake.calls == [('search', '测试花园', 'rent'), ('search', '测试花园', 'neighborhood')]


def test_startup_recovery_does_not_append_new_communities(tmp_path):
    reg = setup(tmp_path)
    directory = tmp_path / 'rentals'; directory.mkdir()
    (directory / 'source_matching_job.json').write_text(json.dumps(dict(
        running=True, phase='running', total=0, remaining=[], outcomes={})))
    fake = FakeDiscovery()
    svc = SourceMatchingService(reg, directory=directory, discovery_factory=lambda **kw: fake)
    svc.resume(); svc._thread.join(5)
    assert fake.calls == []
    assert svc.status()['incremental_count'] == 1


def test_explicit_search_must_not_bind_stale_cached_strong_evidence(tmp_path):
    reg = setup(tmp_path)
    first = strong(); first._homepages[TOTAL_ID] = homepage(seeds=())
    run(service(reg, first, tmp_path))
    second = strong()
    second._homepages[TOTAL_ID] = {**homepage(address='另一条路'), 'longitude': 121.0}
    state = run(service(reg, second, tmp_path))
    assert state['stage'] == STAGE_NEEDS_SELECTION
    assert not any(s['source'] == 'xingfuli' for s in reg.sources())
