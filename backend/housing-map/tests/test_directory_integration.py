import json

from src.services.community_directory import prepare_directory
from src.services.rental_reference.refresh import load_verified_mappings
from src.services import data_loader, auction_history


def test_prepare_once_and_business_delete(tmp_path, monkeypatch):
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([
        {'community_id': '100', 'community_name': '测试花园', 'district': '滨江'}]), encoding='utf-8')
    (tmp_path / 'rental_community_mappings.json').write_text(json.dumps({'version': 1, 'mappings': [
        {'source': 'fang', 'community_id': '100', 'source_community_id': '123',
         'source_name': '测试花园', 'status': 'verified'}]}), encoding='utf-8')
    store = prepare_directory(tmp_path)
    monkeypatch.setattr(data_loader, 'get_data_paths', lambda: {'communities': tmp_path / 'binjiang_communities.json'})
    store.update('100', name='人工标准名', aliases=['测试花园'])
    assert prepare_directory(tmp_path).communities()[0]['community_name'] == '人工标准名'
    assert data_loader.load_communities()[0]['community_name'] == '人工标准名'
    assert load_verified_mappings(tmp_path / 'rental_community_mappings.json') == [('123', '100')]
    store.delete('100')
    assert data_loader.load_communities() == []
    assert load_verified_mappings(tmp_path / 'rental_community_mappings.json') == []
    assert (tmp_path / 'directory-backup' / 'binjiang_communities.json').exists()


def test_auction_manual_reject_not_automatically_name_matched(tmp_path, monkeypatch):
    from src.services.community_registry import CommunityRegistry
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    store.create('测试花园', community_id='100', district='滨江')
    r = store.ingest(dict(source='laipai', source_kind='asset', source_id='1', name='测试花园', district='滨江'))
    store.associate(r['id'], '100')
    path = tmp_path / 'auction_community_mappings.json'
    monkeypatch.setattr(auction_history, 'MAPPING_PATH', path)
    row = dict(source='laipai', asset_id='1', auction_id='2', community_name='测试花园')
    mappings = auction_history.load_mappings(path, store.communities())
    assert auction_history.associate_records([row], store.communities(), mappings)[0]['community_id'] == '100'
    store.unlink(r['id'])
    assert auction_history.associate_records([row], store.communities(), {}) == []
    store.associate(r['id'], '100')
    store.delete('100')
    assert auction_history.associate_records([row], [], {}, keep_unmatched=True) == []
