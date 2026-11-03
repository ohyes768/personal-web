import pytest

from src.services.community_registry import CommunityRegistry


def record(sid='f1', name='测试花园', address='测试路1号'):
    # A non-retired external source: the retired Fang source can no longer be
    # associated, so the generic ingest/auto-association behaviour needs a
    # source that is still allowed.
    return dict(source='laipai', source_kind='community', source_id=sid,
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
    assert store.is_ignored('laipai', 'community', 'f1')
    assert store.ingest(record(name='改名'))['status'] == 'ignored'
    assert all(r['status'] == 'ignored' for r in store.sources())
    assert store.events('c1')[0]['action'] == 'delete'
    store.restore('c1')
    assert len(store.communities()) == 1
    assert not store.is_ignored('laipai', 'community', 'f1')


def test_no_name_blacklist_and_merge_history(tmp_path):
    store = registry(tmp_path)
    store.ingest(record())
    other = store.create('别的小区', district='滨江')
    store.merge('c1', other['community_id'])
    assert store.resolve('c1') == other['community_id']
    assert store.sources()[0]['community_id'] == other['community_id']
    store.delete(other['community_id'])
    assert not store.is_ignored('laipai', 'community', 'new-id')
    assert store.ingest(record('new-id'))['community_id'] is None


def test_deleted_target_rejects_late_association(tmp_path):
    store = registry(tmp_path)
    item = store.ingest(record(address=''))
    store.delete('c1')
    with pytest.raises(ValueError):
        store.associate(item['id'], 'c1')


def test_retired_fang_source_cannot_be_associated_anymore(tmp_path):
    """房天下来源已退役：不能再建立新关联，历史关联仍可读取。"""
    import pytest
    from src.services.rental_reference.providers import active_sources
    store = registry(tmp_path)
    item = store.ingest(dict(source='fang', source_kind='community', source_id='f1',
                             name='风雅钱塘', district='滨江'))
    with pytest.raises(ValueError, match='房天下'):
        store.associate(item['id'], 'c1')
    assert active_sources(store) == {}


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
