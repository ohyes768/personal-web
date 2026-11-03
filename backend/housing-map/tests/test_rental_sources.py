"""Source management reads the community registry only; Fang entries are retired."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import rental_routes, rental_source_routes
from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION
from src.services.rental_reference.refresh import RentalRefreshService, load_verified_mappings
from src.services.rental_reference.sources import SourceRegistryUnavailable, SourceStore
from src.services.rental_reference.storage import RentalPublishLock


def registry(data_dir):
    reg = CommunityRegistry(data_dir / 'community_registry.sqlite3')
    community = reg.create('测试花园', district='滨江', address='测试路1号', community_id='c1')
    fact = reg.ingest(dict(source='tmsf', source_id='t1', name='测试花园', district='滨江',
                           address='测试路1号', property_type='住宅', listing_count=3,
                           market_state='second_hand'))
    reg.associate(fact['id'], community['community_id'])
    with reg.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    return reg


def rental_source(reg, kind='xingfuli', sid='123'):
    row = reg.ingest(dict(source=kind, source_id=sid, name='测试花园', district='滨江',
                          address='测试路1号', seed_listing_id=sid,
                          auto_association_disabled=True,
                          source_url='https://m.xflapp.com/zufang/neighbor-house-list/hz-123.html'))
    if kind == 'fang':
        # Retired Fang associations only exist as historical ledger rows.
        with reg.db() as db:
            db.execute("UPDATE sources SET cid=?,status='matched',method='manual' WHERE id=?",
                       ('c1', row['id']))
    else:
        reg.associate(row['id'], 'c1')
    return row


def test_source_store_requires_the_authoritative_registry(tmp_path):
    path = tmp_path / 'data' / 'rental_community_mappings.json'
    with pytest.raises(SourceRegistryUnavailable):
        SourceStore(path)
    # No second mapping database is created behind the user's back.
    assert not (tmp_path / 'data' / 'rental_sources.sqlite3').exists()


def test_source_store_reads_only_the_current_xingfuli_mapping(tmp_path):
    reg = registry(tmp_path / 'data')
    rental_source(reg, 'fang', '999')
    rental_source(reg, 'xingfuli', '123')
    store = SourceStore(tmp_path / 'data' / 'rental_community_mappings.json')
    mapping = store.get('c1')['mapping']
    assert mapping['source'] == 'xingfuli'
    assert mapping['source_community_id'] == '123'
    assert store.get('c1')['candidates'] == []
    assert store.all_mappings()['c1']['source'] == 'xingfuli'


def test_historical_fang_only_community_has_no_current_mapping(tmp_path):
    reg = registry(tmp_path / 'data')
    rental_source(reg, 'fang', '999')
    store = SourceStore(tmp_path / 'data' / 'rental_community_mappings.json')
    assert store.get('c1')['mapping'] is None
    assert load_verified_mappings(tmp_path / 'data' / 'rental_community_mappings.json') == []


def test_remove_unlinks_xingfuli_and_never_falls_back_to_fang(tmp_path):
    reg = registry(tmp_path / 'data')
    rental_source(reg, 'fang', '999')
    rental_source(reg, 'xingfuli', '123')
    store = SourceStore(tmp_path / 'data' / 'rental_community_mappings.json')
    store.remove('c1')
    assert store.get('c1')['mapping'] is None
    assert load_verified_mappings(tmp_path / 'data' / 'rental_community_mappings.json') == []
    # The historical Fang association is untouched, it is simply not current.
    assert any(r['source'] == 'fang' for r in reg.sources())


def test_source_edits_block_active_worker_and_cli(tmp_path, monkeypatch):
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'mapping.json')
    from src.services.rental_reference.refresh import RefreshAlreadyRunning
    monkeypatch.setattr(service, '_has_active_thread', lambda: True)
    with pytest.raises(RefreshAlreadyRunning): service.change_sources(lambda: None)
    monkeypatch.setattr(service, '_has_active_thread', lambda: False)
    with RentalPublishLock(tmp_path / 'rentals' / 'rental_publish'):
        with pytest.raises(RefreshAlreadyRunning): service.change_sources(lambda: None)


def test_snapshot_not_used_after_unlink_or_rebind():
    current = {'communities': {'c1': {'source': 'xingfuli', 'source_community_id': '123',
                                      'samples': [1]}}}
    assert rental_routes._mapped_entry(current, 'c1', {}) is None
    assert rental_routes._mapped_entry(current, 'c1', {'c1': '456'}) is None
    assert rental_routes._mapped_entry(current, 'c1', {'c1': '123'})['samples'] == [1]


@pytest.fixture
def api(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    path = data_dir / 'rental_community_mappings.json'
    registry(data_dir)
    monkeypatch.setattr(rental_routes, '_mappings_path', path)
    monkeypatch.setattr(rental_routes, '_rentals_dir', tmp_path / 'rentals')
    monkeypatch.setattr(rental_routes, '_service', None)
    monkeypatch.setattr(rental_source_routes, 'load_communities',
                        lambda: [{'community_id': 'c1', 'community_name': '测试花园'}])
    app = FastAPI(); app.include_router(rental_source_routes.router, prefix='/api')
    with TestClient(app) as client:
        yield client


def test_api_retired_fang_endpoints_have_no_side_effect(api, tmp_path):
    path = '/api/communities/c1/rental-source'
    assert api.get(path).json()['data']['mapping'] is None
    assert api.put(path, json={'source_community_id': '123'}).status_code == 410
    assert api.post(path + '/search', json={}).status_code == 410
    assert api.delete(path + '/candidates/123').status_code == 410
    assert api.delete(path).json()['data']['mapping'] is None
    assert api.get('/api/communities/unknown/rental-source').status_code == 404
    # The retired writes never create a second mapping database.
    assert not (tmp_path / 'data' / 'rental_sources.sqlite3').exists()


def test_api_cannot_import_fang_links(api):
    path = '/api/communities/c1/rental-source/search'
    response = api.post(path, json={'source_url': 'https://zu.fang.com/hz/house-xm123/'})
    assert response.status_code == 410
    assert '幸福里' in response.json()['detail']


def test_api_reports_missing_registry_as_unavailable(tmp_path, monkeypatch):
    path = tmp_path / 'data' / 'rental_community_mappings.json'
    monkeypatch.setattr(rental_routes, '_mappings_path', path)
    monkeypatch.setattr(rental_source_routes, 'load_communities',
                        lambda: [{'community_id': 'c1', 'community_name': '测试花园'}])
    app = FastAPI(); app.include_router(rental_source_routes.router, prefix='/api')
    with TestClient(app) as client:
        assert client.get('/api/communities/c1/rental-source').status_code == 503


def test_api_returns_only_the_current_xingfuli_mapping(api, tmp_path):
    reg = CommunityRegistry(tmp_path / 'data' / 'community_registry.sqlite3')
    rental_source(reg, 'fang', '999')
    rental_source(reg, 'xingfuli', '123')
    data = api.get('/api/communities/c1/rental-source').json()['data']
    assert data['mapping']['source'] == 'xingfuli'
    assert data['candidates'] == []
