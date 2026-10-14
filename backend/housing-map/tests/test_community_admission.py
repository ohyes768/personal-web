import json

import pytest

from src.services.community_directory import prepare_directory
from src.services.community_registry import CommunityRegistry


def seeded(tmp_path):
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([
        {'community_id': '100', 'community_name': '江汉路小区', 'district': '滨江', 'address': '滨江区江汉路1号'},
        {'community_id': '200', 'community_name': '未知花园', 'district': '滨江', 'address': '滨江区测试路2号'}]), encoding='utf-8')
    (tmp_path / 'property_types.json').write_text(json.dumps({'100': {'property_type': '住宅'}}), encoding='utf-8')
    (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({
        '100': {'formatted_address': '滨江区江汉路1号'},
        '200': {'formatted_address': '滨江区测试路2号'}}), encoding='utf-8')
    return prepare_directory(tmp_path)


def test_migration_is_once_and_manual_review_survives_refresh_restart(tmp_path):
    store = seeded(tmp_path)
    assert store.admission('100')['state'] == 'admitted'
    assert store.admission('200')['state'] == 'pending'
    first = store.admission('100')
    moved = store.decide_admission('100', 'review', revision=first['revision'], reason='疑似道路')
    assert moved['state'] == 'pending' and moved['auto_review_locked']
    store.ingest(dict(source='tmsf', source_id='100', name='江汉路小区', property_type='别墅'))
    restarted = prepare_directory(tmp_path)
    assert restarted.admission('100') == moved
    assert len(restarted.communities()) == 2
    assert restarted.sources()[0]['status'] == 'matched'
    assert (tmp_path / 'directory-backup' / 'community_registry-before-admission.sqlite3').exists()


def test_exclude_restore_and_explicit_admit_preserve_sources(tmp_path):
    store = seeded(tmp_path)
    auction = store.ingest(dict(source='laipai', source_kind='asset', source_id='asset1',
                               name='江汉路小区', auction_ids=['round1', 'round2']))
    store.associate(auction['id'], '100')
    before = store.sources()
    excluded = store.decide_admission('100', 'exclude', revision=1, reason='不是住宅小区')
    assert excluded['state'] == 'excluded'
    restored = store.decide_admission('100', 'restore-admission', revision=2)
    assert restored['state'] == 'pending' and restored['auto_review_locked']
    admitted = store.decide_admission('100', 'admit', revision=3, property_type='住宅')
    assert admitted['state'] == 'admitted' and not admitted['auto_review_locked']
    assert store.sources() == before
    assert not store.is_ignored('laipai', 'auction', 'round1')
    store.decide_admission('100', 'review', revision=4, reason='重新核对')
    store.ingest(dict(source='laipai', source_kind='asset', source_id='asset1', name='江汉路小区', auction_ids=['round3']))
    assert store.admission('100')['auto_review_locked']
    assert next(r for r in store.sources() if r['id'] == auction['id'])['auction_ids'] == ['round1', 'round2', 'round3']


def test_conflict_validation_and_new_sources_cannot_bypass_admission(tmp_path):
    store = seeded(tmp_path)
    with pytest.raises(ValueError, match='版本'):
        store.decide_admission('100', 'review', revision=0)
    with pytest.raises(ValueError, match='原因'):
        store.decide_admission('100', 'exclude', revision=1)
    with pytest.raises(ValueError, match='住宅'):
        store.decide_admission('100', 'admit', revision=1, property_type='公寓')
    source = store.ingest(dict(source='tmsf', source_id='new', name='新花园', property_type='住宅'))
    new = store.create_from_source(source['id'], name='新花园', aliases=[], district='滨江', address='')
    assert prepare_directory(tmp_path).admission(new['community_id'])['state'] == 'pending'
    assert store.admission('100')['revision'] == 1
    store.delete('200')
    with pytest.raises(ValueError):
        store.decide_admission('200', 'admit', revision=1, property_type='住宅')


def test_manual_confirmation_keeps_effective_type_and_reports_conflict(tmp_path):
    store = seeded(tmp_path)
    store.decide_admission('100', 'admit', revision=1, property_type='排屋')
    store.ingest(dict(source='tmsf', source_id='100', name='江汉路小区', property_type='写字楼'))
    from src.services.community_admission import community_views
    view = next(c for c in community_views(store, tmp_path) if c['community_id'] == '100')
    assert view['admission']['state'] == 'admitted'
    assert view['effective_property_type'] == '排屋'
    assert view['admission_conflict']


def test_existing_sqlite_migration_preserves_manual_identities_and_deleted_rows(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    store.create('人工标准名', community_id='local-old', district='滨江', aliases=['原名'])
    source = store.ingest(dict(source='tmsf', source_id='99', name='原名', property_type='别墅'))
    store.associate(source['id'], 'local-old')
    store.create('已删除花园', community_id='deleted')
    store.delete('deleted', '历史删除')
    with store.db() as db:
        # Simulate a pre-admission directory, including its preparation marker.
        db.execute('DELETE FROM community_admission')
        db.execute("INSERT INTO meta VALUES ('prepared','1')")
        db.execute('INSERT INTO rejected VALUES (?,?)', ('rejected-source', 'local-old'))
    before = store.sources()
    from src.services.community_admission import migrate_admission
    migrate_admission(store, tmp_path)
    assert store.admission('local-old')['state'] == 'admitted'
    assert store.admission('local-old')['property_type'] == '别墅'
    assert prepare_directory(tmp_path).sources() == before
    assert store.communities()[0]['aliases'] == ['原名']
    assert store.communities(True)[0]['community_id'] == 'deleted'
    assert store.admission('deleted')['state'] == 'excluded'
    event_count = len(store.events('local-old'))
    migrate_admission(store, tmp_path)
    assert len(store.events('local-old')) == event_count
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM rejected').fetchone()[0] == 1


def test_migrated_admission_tracks_current_types_and_conflicts(tmp_path):
    from src.services.community_admission import community_views
    store = seeded(tmp_path)
    store.ingest(dict(source='tmsf', source_id='100', name='江汉路小区', property_type='别墅'))
    item = next(c for c in community_views(store, tmp_path) if c['community_id'] == '100')
    assert item['effective_property_type'] == '别墅'
    store.ingest(dict(source='tmsf', source_id='100', name='江汉路小区', property_type='写字楼'))
    item = next(c for c in community_views(store, tmp_path) if c['community_id'] == '100')
    assert item['admission_state'] == 'pending' and item['map_status'] == 'not_admitted'
    assert item['admission_conflict']
