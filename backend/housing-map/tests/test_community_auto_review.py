import json

import pytest

from src.services.community_registry import CommunityRegistry
from src.services.community_review import ReviewWorkspace


def setup(tmp_path):
    from src.services.community_auto_review import AutoReview
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    return store, AutoReview(store, tmp_path)


def add(store, sid='1', **values):
    return store.ingest({**dict(source='tmsf', source_id=sid, name='清河花园', district='滨江',
                             address='滨江区清河路1号', property_type='住宅'), **values})


def test_preview_readonly_reproducible_and_execution_explicit(tmp_path):
    store, auto = setup(tmp_path)
    add(store)
    before = store.path.read_bytes()
    preview = auto.preview()
    assert preview == auto.preview() and store.path.read_bytes() == before
    assert preview['counts']['admit'] == 1 and store.communities() == []
    with pytest.raises(ValueError, match='启用'):
        auto.execute(preview['snapshot_id'])
    auto.configure(True, preview['snapshot_id'])
    report = auto.execute(preview['snapshot_id'])
    assert report['counts']['applied'] == 1
    cid = store.communities()[0]['community_id']
    assert store.admission(cid)['decision_kind'] == 'automatic'
    assert store.admission(cid)['rule_version'] and store.admission(cid)['evidence']
    assert auto.preview()['counts']['admit'] == 0
    with pytest.raises(ValueError):
        auto.execute(preview['snapshot_id'])
    store.decide_admission(cid, 'review', revision=store.admission(cid)['revision'])
    assert auto.preview()['counts']['admit'] == 0
    store.decide_admission(cid, 'exclude', revision=store.admission(cid)['revision'], reason='误收录')
    store.decide_admission(cid, 'restore-admission', revision=store.admission(cid)['revision'])
    assert auto.preview()['items'][0]['action'] == 'pending'


@pytest.mark.parametrize('patch', [
    {'source': 'amap', 'name': '江汉路小区'}, {'source': 'laipai', 'auction_title': '住宅拍卖'},
    {'property_type': '公寓'}, {'property_type': '其他'}, {'property_type': '住宅/商贸'},
    {'property_type_conflict': True}, {'address': ''}, {'district': '上城'},
    {'name': '清河花园停车场'}, {'auto_association_disabled': True},
])
def test_uncertain_evidence_never_admitted(tmp_path, patch):
    store, auto = setup(tmp_path)
    record = dict(source='tmsf', source_id='1', name='清河花园', district='滨江', address='滨江区清河路1号', property_type='住宅')
    store.ingest({**record, **patch})
    assert auto.preview()['counts']['admit'] == 0


def test_duplicates_conflicts_deleted_and_identity_veto(tmp_path):
    store, auto = setup(tmp_path)
    add(store)
    add(store, '2', address='滨江区清河路2号')
    assert auto.preview()['counts']['admit'] == 0
    assert all(i['reasons'] for i in auto.preview()['items'])
    store.ignore_source(store.sources()[1]['id'])
    cid = store.create('清河花园', district='滨江', address='滨江区清河路1号')['community_id']
    store.delete(cid, '历史删除')
    assert auto.preview()['counts']['admit'] == 0


def test_new_source_id_cannot_bypass_manual_exclusion_but_different_address_not_blacklisted(tmp_path):
    store, auto = setup(tmp_path)
    add(store)
    work = ReviewWorkspace(store, tmp_path)
    row = work.reviews()[0]
    work.decide(row['id'], 'exclude', revision=row['revision'], reason='不收录')
    add(store, 'new')
    assert auto.preview()['counts']['admit'] == 0
    add(store, 'elsewhere', name='另一花园', address='滨江区清河路3号')
    assert auto.preview()['counts']['admit'] == 1


def test_stale_preview_master_change_and_facts_change(tmp_path):
    store, auto = setup(tmp_path)
    add(store)
    preview = auto.preview()
    auto.configure(True, preview['snapshot_id'])
    add(store, '2', name='另一个花园')
    with pytest.raises(ValueError, match='变化'):
        auto.execute(preview['snapshot_id'])
    preview = auto.preview()
    (tmp_path / 'property_types.json').write_text(json.dumps({'1': {'property_type': '商贸'}}))
    with pytest.raises(ValueError, match='变化'):
        auto.execute(preview['snapshot_id'])


def test_legacy_association_cannot_bypass_withdrawn_master(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    cid = store.create('清河花园', district='滨江', address='滨江区清河路1号')['community_id']
    store.decide_admission(cid, 'review', revision=1)
    source = add(store)
    assert source['status'] == 'pending'


def test_new_identity_legacy_auto_bind_honors_excluded_candidate(tmp_path):
    store, auto = setup(tmp_path)
    add(store)
    work = ReviewWorkspace(store, tmp_path)
    row = work.reviews()[0]
    work.decide(row['id'], 'exclude', revision=row['revision'], reason='人工排除身份')
    cid = store.create('清河花园', district='滨江', address='滨江区清河路1号')['community_id']
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    assert add(store, 'changed-id')['status'] == 'pending'


def test_batch_member_collision_rolls_back_whole_candidate(tmp_path, monkeypatch):
    store, auto = setup(tmp_path)
    add(store); add(store, '2', source='amap')
    preview = auto.preview(); auto.configure(True, preview['snapshot_id'])
    original = store._associate
    def failing(db, rid, cid, **kwargs):
        row = db.execute('SELECT source FROM sources WHERE id=?', (rid,)).fetchone()
        if row[0] == 'amap':
            raise ValueError('模拟来源冲突')
        return original(db, rid, cid, **kwargs)
    monkeypatch.setattr(store, '_associate', failing)
    report = auto.execute(preview['snapshot_id'])
    assert report['counts']['conflict'] == 1 and store.communities() == []
    assert all(m['status'] == 'pending' for m in store.sources())


def test_alias_changed_address_does_not_match_by_position(tmp_path):
    store, auto = setup(tmp_path)
    cid = store.create('清河花园', district='滨江', address='滨江区清河路2号',
                       longitude=120.19, latitude=30.20, coordinate_system='gcj02')['community_id']
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    assert add(store, longitude=120.19, latitude=30.20, coordinate_system='gcj02')['status'] == 'pending'
    assert auto.preview()['counts']['merge'] == 0


def test_preview_cli_diagnostic_report_has_no_business_writes(tmp_path, monkeypatch):
    from src.services.community_auto_review import main
    store, _ = setup(tmp_path); add(store)
    before = store.path.read_bytes()
    monkeypatch.setattr('sys.argv', ['auto-review', '--data-dir', str(tmp_path), '--report'])
    assert main() == 0 and before == store.path.read_bytes()
    reports = list((tmp_path / 'diagnostics' / 'auto-review').glob('*.json'))
    assert len(reports) == 1 and json.loads(reports[0].read_text(encoding='utf-8'))['counts']['admit'] == 1


def test_split_locks_both_halves_and_does_not_recombine_after_child_admit(tmp_path):
    store, auto = setup(tmp_path)
    add(store); add(store, '2', source='amap')
    work = ReviewWorkspace(store, tmp_path); row = work.reviews()[0]
    child = work.split(row['id'], revision=row['revision'], member_ids=[row['members'][0]['id']])
    rows = work.reviews()
    assert all(r['auto_review_locked'] for r in rows)
    work.decide(child['id'], 'admit', revision=child['revision'], name='清河花园', property_type='住宅')
    assert auto.preview()['counts']['merge'] == 0
