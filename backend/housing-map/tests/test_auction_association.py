import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services import auction_association, auction_history, auction_refresh
from src.services.community_directory import prepare_directory
from src.services.auction_store import read_store, StoreLock
from src.api import auction_routes, directory_routes


def row(aid='1', asset='a', name='测试花园', **changes):
    return dict(source='laipai', auction_id=aid, asset_id=asset, community_name=name,
                title='滨江区住宅', address='测试路1号', status='todo', captured_at='2026-10-13', **changes)


def save(path, rows):
    path.write_text(json.dumps(dict(version=1, records=rows)))


def test_sync_groups_rounds_and_preserves_manual_decisions(tmp_path):
    path = tmp_path / 'auction_records.json'
    store = prepare_directory(tmp_path)
    store.create('测试花园', district='滨江', address='测试路1号', community_id='local-test')
    save(path, [row(), row('2'), row('3', 'b', '不同小区')])
    report = auction_association.sync_records(path)
    assert report == dict(records=3, identities=2, matched=1, automatic=1, pending=1, ignored=0)
    assert len(store.sources()) == 2
    source = next(r for r in store.sources() if r['source_id'] == 'a')
    assert source['auction_ids'] == ['1', '2']
    store.unlink(source['id'])
    assert auction_association.sync_records(path)['pending'] == 2
    store.associate(source['id'], 'local-test')
    assert auction_association.sync_records(path)['matched'] == 1
    assert next(r for r in store.sources() if r['source_id'] == 'a')['method'] == 'manual'
    store.delete('local-test')
    assert auction_association.sync_records(path)['ignored'] == 1
    assert len(store.sources()) == 2
    assert len(auction_association.pending_records(path)[0]) == 1


def test_missing_name_never_auto_matches_title_and_missing_asset_is_per_round(tmp_path):
    path = tmp_path / 'auction_records.json'
    store = prepare_directory(tmp_path)
    store.create('滨江区住宅', district='滨江', address='测试路1号', community_id='c')
    save(path, [row(name=''), row('2', '', ''), row('3', None, '')])
    assert auction_association.sync_records(path)['pending'] == 3
    assert store.auto_associate() == 0
    pending, needs_sync = auction_association.pending_records(path)
    assert not needs_sync and len(pending) == 3
    assert all('未提供' in p['reason'] for p in pending)


def test_old_records_need_explicit_sync_and_binding_updates_all_rounds(tmp_path, monkeypatch):
    path = tmp_path / 'auction_records.json'
    save(path, [row(), row('2')])
    assert auction_association.pending_records(path) == ([], True)
    monkeypatch.setattr(auction_routes, 'AUCTION_PATH', path)
    monkeypatch.setattr(auction_history, 'MAPPING_PATH', tmp_path / 'auction_community_mappings.json')
    monkeypatch.setattr(directory_routes, 'DATA_DIR', tmp_path)
    store = prepare_directory(tmp_path)
    store.create('另一个名称', district='滨江', address='', community_id='local-test')
    monkeypatch.setattr(auction_history, 'load_communities', lambda: store.communities())
    app = FastAPI()
    app.include_router(auction_routes.router, prefix='/api')
    app.include_router(directory_routes.router, prefix='/api')
    with TestClient(app) as api:
        assert api.post('/api/auctions/associations/sync').status_code == 200
        data = api.get('/api/auctions/associations/pending').json()['data']
        assert data['total'] == 1 and len(data['items'][0]['rounds']) == 2
        rid = data['items'][0]['record_id']
        assert api.post(f'/api/directory/sources/{rid}/associate', json={'community_id': 'local-test'}).status_code == 200
        assert api.get('/api/auctions/associations/pending').json()['data']['total'] == 0
        rows = api.get('/api/auctions?association=matched').json()['data']['records']
        assert len(rows) == 2 and all(r['community_id'] == 'local-test' for r in rows)
        with StoreLock(path):
            assert api.post('/api/auctions/associations/sync').status_code == 409
        assert api.get('/api/auctions/associations/pending?page=0').status_code == 422
        assert api.post('/api/auctions/associations/sync').json()['data']['matched'] == 1


def test_sync_ignored_round_does_not_create_new_asset(tmp_path):
    path = tmp_path / 'auction_records.json'
    store = prepare_directory(tmp_path)
    source = store.ingest(dict(source='laipai', source_kind='auction', source_id='1', name='测试花园'))
    store.ignore_source(source['id'])
    save(path, [row()])
    assert auction_association.sync_records(path)['ignored'] == 1
    assert len(store.sources()) == 1
    assert auction_association.pending_records(path) == ([], False)


def test_collection_sync_failure_keeps_saved_records(tmp_path, monkeypatch):
    class Client:
        def list_page(self, page):
            return dict(count=1, list=[dict(auction_id=1, area_code=330108)])
        def detail(self, aid):
            return dict(auction_id=aid, object_id='1', area_code=330108, second_class='residence',
                        object_title='滨江区住宅', object_address='滨江区测试路1号', cell_name='测试花园',
                        auction_status='todo')
    path = tmp_path / 'auction_records.json'
    def broken(_):
        raise OSError('database unavailable')
    monkeypatch.setattr(auction_association, 'sync_records', broken)
    report = auction_refresh.collect_auctions(path, client=Client(), communities=[], delay=0)
    assert report['saved'] == 1 and 'error' in report['association']
    assert len(read_store(path)['records']) == 1


def test_asset_identity_upgrade_keeps_manual_binding_and_rejection(tmp_path):
    path = tmp_path / 'auction_records.json'
    store = prepare_directory(tmp_path)
    store.create('测试花园', district='滨江', address='测试路1号', community_id='c')
    source = store.ingest(dict(source='laipai', source_kind='auction', source_id='1', name='旧名称'))
    store.associate(source['id'], 'c')
    save(path, [row(), row('2')])
    assert auction_association.sync_records(path)['matched'] == 1
    assert len(store.sources()) == 1
    upgraded = store.sources()[0]
    assert upgraded['id'] == source['id'] and upgraded['source_kind'] == 'asset'
    assert upgraded['method'] == 'manual' and upgraded['auction_ids'] == ['1', '2']
    store.unlink(upgraded['id'])
    assert auction_association.sync_records(path)['pending'] == 1


def test_multiple_legacy_round_decisions_remain_pending_on_repeated_sync(tmp_path):
    path = tmp_path / 'auction_records.json'
    store = prepare_directory(tmp_path)
    store.create('测试花园', district='滨江', address='测试路1号', community_id='c')
    for aid in ('1', '2'):
        store.ingest(dict(source='laipai', source_kind='auction', source_id=aid, name='旧名'))
    save(path, [row(), row('2')])
    assert auction_association.sync_records(path)['pending'] == 1
    assert auction_association.sync_records(path)['pending'] == 1
    assert '独立关联决定' in auction_association.pending_records(path)[0][0]['reason']
