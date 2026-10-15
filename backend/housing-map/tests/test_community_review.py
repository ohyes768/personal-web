import pytest

from src.services.community_registry import CommunityRegistry


def source(store, sid, *, name='测试花园', address='滨江区测试路1号', source='amap', **extra):
    return store.ingest(dict(source=source, source_id=sid, name=name, district='滨江', address=address, **extra))


def workspace(tmp_path):
    from src.services.community_review import ReviewWorkspace
    return ReviewWorkspace(CommunityRegistry(tmp_path / 'community_registry.sqlite3'), tmp_path)


def test_group_stability_and_no_same_name_different_address_or_phase_merge(tmp_path):
    work = workspace(tmp_path)
    source(work.store, '1', source='tmsf', property_type='住宅')
    source(work.store, '2')
    source(work.store, '3', address='滨江区另一条路')
    source(work.store, '4', name='测试花园二期')
    reviews = work.reviews()
    assert len(reviews) == 3
    grouped = next(r for r in reviews if len(r['members']) == 2)
    assert {m['source'] for m in grouped['members']} == {'tmsf', 'amap'}
    assert work.reviews() == reviews
    result = work.decide(grouped['id'], 'admit', revision=grouped['revision'], name='标准花园', property_type='住宅')
    assert work.summary()['residential'] == 1 and work.summary()['pending'] == 2
    assert len(work.store.communities()) == 1
    assert all(r['community_id'] == result['community_id'] for r in work.store.sources() if r['source_id'] in {'1', '2'})
    with pytest.raises(ValueError):
        work.decide(grouped['id'], 'admit', revision=grouped['revision'], name='标准花园', property_type='住宅')


def test_exclusion_restore_lock_and_new_rounds_do_not_revive(tmp_path):
    work = workspace(tmp_path)
    source(work.store, 'asset1', source='laipai', source_kind='asset', auction_ids=['1', '2'])
    source(work.store, 'asset2', source='laipai', source_kind='asset', auction_ids=['3'])
    row = work.reviews()[0]
    assert row['auction_assets'] == 2 and row['auction_rounds'] == 3
    work.decide(row['id'], 'exclude', revision=row['revision'], reason='不是独立小区')
    source(work.store, 'asset1', source='laipai', source_kind='asset', auction_ids=['4'])
    assert work.reviews() == []
    excluded = work.reviews(state='excluded')[0]
    assert excluded['auto_review_locked'] and excluded['auction_rounds'] == 4
    work.restore(excluded['id'], revision=excluded['revision'])
    restored = work.reviews()[0]
    assert restored['auto_review_locked']
    assert all(s['status'] == 'pending' for s in work.store.sources())


def test_split_and_stale_members_roll_back_and_fang_uniqueness(tmp_path):
    work = workspace(tmp_path)
    one = source(work.store, '1', source='fang')
    source(work.store, '2', source='fang')
    row = work.reviews()[0]
    with pytest.raises(ValueError, match='房天下'):
        work.decide(row['id'], 'admit', revision=row['revision'], name='花园', property_type='住宅')
    assert work.store.communities() == []
    work.split(row['id'], revision=row['revision'], member_ids=[one['id']])
    assert len(work.reviews()) == 2
    assert len(work.reviews()) == 2  # A refresh must never undo a human split.
    selected = next(r for r in work.reviews() if one['id'] in [m['id'] for m in r['members']])
    work.store.ignore_source(one['id'])
    with pytest.raises(ValueError):
        work.decide(selected['id'], 'admit', revision=selected['revision'], name='花园', property_type='住宅')
    assert work.store.communities() == []


def test_existing_master_review_and_merge_keep_identity_and_manual_veto(tmp_path):
    work = workspace(tmp_path)
    work.store.create('原花园', community_id='old', district='滨江')
    s = source(work.store, '1', name='原花园')
    work.store.associate(s['id'], 'old')
    work.store.decide_admission('old', 'review', revision=1, reason='待核对重复')
    work.store.create('住宅花园', community_id='target', district='滨江')
    work.store.decide_admission('target', 'admit', revision=1, property_type='住宅')
    row = work.reviews()[0]
    assert row['existing_cid'] == 'old' and row['auto_review_locked']
    work.decide(row['id'], 'merge', revision=row['revision'], target_id='target')
    assert work.store.resolve('old') == 'target'
    assert work.summary()['residential'] == 1 and work.summary()['pending'] == 0
    assert work.store.sources()[0]['community_id'] == 'target'


def test_position_groups_require_all_pair_evidence_not_distance_chain(tmp_path):
    work = workspace(tmp_path)
    for sid, lng in [('1', 120.207), ('2', 120.2079), ('3', 120.2088)]:
        source(work.store, sid, address='', longitude=lng, latitude=30.2, coordinate_system='gcj02')
    assert sorted(len(r['members']) for r in work.reviews(state='excluded')) == [1, 2]


def test_excluded_source_cannot_auto_bind_and_unlinked_member_requeues(tmp_path):
    work = workspace(tmp_path)
    item = source(work.store, '1')
    row = work.reviews()[0]
    work.decide(row['id'], 'exclude', revision=row['revision'], reason='人工排除')
    work.store.create('测试花园', community_id='target', district='滨江', address='滨江区测试路1号')
    work.store.decide_admission('target', 'admit', revision=1, property_type='住宅')
    work.store.auto_associate()
    assert work.store.sources()[0]['status'] == 'pending'

    excluded = work.reviews(state='excluded')[0]
    with pytest.raises(ValueError, match='审核'):
        work.store.associate(item['id'], 'target')
    with pytest.raises(ValueError, match='审核'):
        work.store.create_from_source(item['id'], name='花园', aliases=[], district='滨江', address='')
    work.restore(excluded['id'], revision=excluded['revision'])
    restored = work.reviews()[0]
    work.decide(restored['id'], 'merge', revision=restored['revision'], target_id='target')
    work.store.unlink(item['id'])
    new = work.reviews()[0]
    assert new['state'] == 'pending'
    assert work.store.sources()[0]['status'] == 'pending'


def test_selected_members_are_decided_atomically_without_affecting_remainder(tmp_path):
    work = workspace(tmp_path)
    one = source(work.store, '1')
    source(work.store, '2', source='tmsf')
    row = work.reviews()[0]
    work.decide(row['id'], 'admit', revision=row['revision'], member_ids=[one['id']], name='测试花园', property_type='住宅')
    assert work.summary()['residential'] == 1 and work.summary()['pending'] == 1
    assert next(s for s in work.store.sources() if s['id'] == one['id'])['status'] == 'matched'


def test_current_master_member_change_rejects_stale_review(tmp_path):
    work = workspace(tmp_path)
    work.store.create('测试花园', community_id='old')
    one = source(work.store, '1'); work.store.associate(one['id'], 'old')
    row = work.reviews()[0]
    source(work.store, '1', property_type='写字楼')
    with pytest.raises(ValueError, match='变化'):
        work.decide(row['id'], 'admit', revision=row['revision'], name='测试花园', property_type='住宅')
    assert work.store.admission('old')['state'] == 'pending'


def test_collection_completion_materializes_review_without_admitting(tmp_path):
    from src.services.directory_collection import collect_names
    work = workspace(tmp_path)
    def discovered(cancel, ignored):
        yield dict(source='tmsf', source_id='1', name='采集花园', district='滨江')
    report = collect_names(work.store, ['tmsf'], adapters={'tmsf': discovered})
    assert report['phase'] == 'succeeded'
    with work.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM review_candidates').fetchone()[0] == 1
    assert work.store.communities() == []
