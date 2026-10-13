import pytest

from src.services.community_registry import CommunityRegistry


def record(sid='f1', name='测试花园', address='测试路1号'):
    return dict(source='fang', source_kind='community', source_id=sid,
                name=name, district='滨江', address=address)


def registry(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.create('测试花园', district='滨江', address='测试路1号', community_id='c1')
    return store


def test_evidence_match_and_ambiguous_names(tmp_path):
    store = registry(tmp_path)
    first = store.ingest(record())
    assert first['community_id'] == 'c1' and first['method'] == 'auto'
    store.create('测试花园', district='滨江', address='其他路2号')
    assert store.ingest(record('f2'))['community_id'] is None
    assert store.ingest(record('f3', '测试花园一期'))['community_id'] is None


def test_missing_evidence_and_manual_override(tmp_path):
    store = registry(tmp_path)
    item = store.ingest(record(address=''))
    assert item['community_id'] is None
    store.associate(item['id'], 'c1')
    store.ingest(record(name='来源改名', address=''))
    assert store.sources()[0]['method'] == 'manual'
    assert len(store.sources()) == 1
    store.unlink(item['id'])
    store.ingest(record())
    assert store.sources()[0]['community_id'] is None


def test_delete_all_sources_restart_rename_restore(tmp_path):
    store = registry(tmp_path)
    store.ingest(record())
    store.ingest({**record('p1'), 'source': 'amap'})
    store.delete('c1', '不是小区')
    store = CommunityRegistry(store.path)
    assert store.communities() == []
    assert store.is_ignored('fang', 'community', 'f1')
    assert store.ingest(record(name='改名'))['status'] == 'ignored'
    assert all(r['status'] == 'ignored' for r in store.sources())
    assert store.events('c1')[0]['action'] == 'delete'
    store.restore('c1')
    assert len(store.communities()) == 1
    assert not store.is_ignored('fang', 'community', 'f1')


def test_no_name_blacklist_and_merge_history(tmp_path):
    store = registry(tmp_path)
    store.ingest(record())
    other = store.create('别的小区', district='滨江')
    store.merge('c1', other['community_id'])
    assert store.resolve('c1') == other['community_id']
    assert store.sources()[0]['community_id'] == other['community_id']
    store.delete(other['community_id'])
    assert not store.is_ignored('fang', 'community', 'new-id')
    assert store.ingest(record('new-id'))['community_id'] is None


def test_deleted_target_rejects_late_association(tmp_path):
    store = registry(tmp_path)
    item = store.ingest(record(address=''))
    store.delete('c1')
    with pytest.raises(ValueError):
        store.associate(item['id'], 'c1')


def test_rental_skipped_seed_never_requests_upstream():
    from src.services.fang_rentals import crawl_runs
    calls = []
    results = list(crawl_runs(['https://zu.fang.com/hz/house-xm123/'], fetch=lambda url: calls.append(url),
                             skip_seed=lambda _: True))
    assert calls == []
    assert results[0].status == 'list_failed'


def test_create_from_source_is_atomic_and_preserves_position(tmp_path):
    store = registry(tmp_path)
    r = store.ingest(dict(source='amap', source_kind='poi', source_id='p1', name='另一花园',
                         district='滨江', longitude=120.18, latitude=30.18, coordinate_system='gcj02'))
    c = store.create_from_source(r['id'], name='另一花园', aliases=[], district='滨江', address='另一路')
    assert c['longitude'] == 120.18
    assert store.sources()[0]['community_id'] == c['community_id']
    before = len(store.communities())
    with pytest.raises(ValueError):
        store.create_from_source(r['id'], name='重复创建', aliases=[], district='滨江', address='')
    assert len(store.communities()) == before
