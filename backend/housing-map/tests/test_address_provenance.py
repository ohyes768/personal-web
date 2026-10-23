import json
import threading
from types import SimpleNamespace

from src.services.community_directory import prepare_directory, mark_legacy_addresses
from src.services.community_registry import CommunityRegistry, now
from src.services.community_admission import community_views


def legacy_store(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    address = '浙江省杭州市滨江区襄七房'
    store.create('襄七房', district='滨江', address=address, community_id='123')
    source = store.ingest(dict(source='tmsf', source_id='123', name='襄七房', district='滨江', address=address))
    with store.db() as db:
        db.execute("UPDATE sources SET method='import' WHERE id=?", (source['id'],))
    (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({'123': {'formatted_address': address}}))
    mark_legacy_addresses(store, tmp_path)
    return store


def test_empty_address_corrects_legacy_but_failure_does_not(tmp_path):
    store = legacy_store(tmp_path)
    before = store.communities()[0]['address']
    assert store.sources()[0]['address_verification_pending']
    store.ingest(dict(source='tmsf', source_id='123', name='襄七房', property_type_error='timeout'))
    assert store.communities()[0]['address'] == before
    store.ingest(dict(source='tmsf', source_id='123', name='襄七房', address='暂无',
                      address_origin='source_detail', address_checked_at=now(), address_verification_pending=False))
    assert community_views(store, tmp_path)[0]['admission_state'] == 'excluded'
    mark_legacy_addresses(store, tmp_path)
    assert store.communities()[0]['address'] == '暂无'
    assert any(e['action'] == 'address_corrected' for e in store.events('123'))


def test_manual_address_is_preserved(tmp_path):
    store = legacy_store(tmp_path)
    store.update('123', name='襄七房', aliases=[], address='滨江区真实路1号')
    store.ingest(dict(source='tmsf', source_id='123', name='襄七房', address='',
                      address_origin='source_detail', address_checked_at=now()))
    assert community_views(store, tmp_path)[0]['address'] == '滨江区真实路1号'


def test_new_import_keeps_geocoder_separate(tmp_path):
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([dict(community_id='123', community_name='襄七房', district='滨江')]))
    (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({'123': {'formatted_address': '浙江省杭州市滨江区襄七房'}}))
    store = prepare_directory(tmp_path)
    assert store.communities()[0]['address'] == ''
    assert store.sources()[0]['address'] == ''
    assert store.communities()[0]['geographic_address']


def test_type_cache_cannot_skip_address_verification(monkeypatch):
    from src.services import directory_collection, tmsf_property_type, tmsf_fetcher
    from scripts import fetch_tmsf_binjiang_communities
    item = SimpleNamespace(community_id='123', community_name='襄七房', community_alias='', district='滨江', subdistrict='长河', source_url='list')
    monkeypatch.setattr(fetch_tmsf_binjiang_communities, 'fetch_binjiang_communities', lambda: [item])
    monkeypatch.setattr(tmsf_fetcher, 'TmsfClient', lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(directory_collection, 'pause', lambda _: None)
    calls = []
    def fetch(*args):
        calls.append(True)
        return dict(address='未知', property_type='住宅')
    monkeypatch.setattr(tmsf_property_type, 'fetch_community_facts', fetch, raising=False)
    monkeypatch.setattr(tmsf_property_type, 'fetch_property_facts', fetch)
    previous = dict(name='襄七房', address='旧定位', property_type='住宅', property_type_captured_at=now())
    rows = list(directory_collection.tmsf_names(threading.Event(), lambda *_: False, {('community', '123'): previous}))
    facts_rows = [r for r in rows if not r.get('_errors_only')]
    assert calls and facts_rows[-1]['address'] == '未知'
    assert facts_rows[-1]['address_origin'] == 'source_detail' and facts_rows[-1]['address_checked_at']

    # A legacy identity absent from today's directory must still be checked.
    monkeypatch.setattr(fetch_tmsf_binjiang_communities, 'fetch_binjiang_communities', lambda: [])
    previous.update(address_verification_pending=True, district='滨江')
    rows = list(directory_collection.tmsf_names(threading.Event(), lambda *_: False, {('community', '123'): previous}))
    facts_rows = [r for r in rows if not r.get('_errors_only')]
    assert len(calls) == 2 and facts_rows[-1]['address'] == '未知'
    # Verified empty addresses are cached without resurrecting an old address.
    cached = facts_rows[-1]
    cached['address'] = ''
    rows = list(directory_collection.tmsf_names(threading.Event(), lambda *_: False, {('community', '123'): cached}))
    assert not [r for r in rows if not r.get('_errors_only')]  # only pending legacy identities supplement an absent directory
