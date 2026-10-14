import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import directory_routes
from src.services.community_registry import CommunityRegistry
from src.services.community_review import ReviewWorkspace
from tests.test_community_auto_review import add, setup


def test_shared_transaction_merge_and_fang_conflict(tmp_path):
    store, auto = setup(tmp_path)
    cid = store.create('清河花园', district='滨江', address='滨江区清河路1号')['community_id']
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    source = add(store)
    # Preserve a pending source as would be held by a review before identity processing.
    with store.db() as db:
        db.execute("UPDATE sources SET cid=NULL,status='pending' WHERE id=?", (source['id'],))
    preview = auto.preview()
    assert preview['counts']['merge'] == 1
    auto.configure(True, preview['snapshot_id'])
    assert auto.execute(preview['snapshot_id'])['counts']['applied'] == 1
    assert len(store.communities()) == 1 and store.admission(cid)['decision_kind'] == 'manual'
    assert store.sources()[0]['method'] == 'auto'


def test_api_explicit_preview_enable_execute_and_stale(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(directory_routes, 'DATA_DIR', tmp_path)
    app = FastAPI(); app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    add(store)
    before = store.path.read_bytes()
    preview = client.post('/api/directory/auto-review/preview').json()['data']
    assert before == store.path.read_bytes()
    assert client.post('/api/directory/auto-review/execute', json={'snapshot_id': preview['snapshot_id']}).status_code == 409
    assert client.put('/api/directory/auto-review/config', json={'enabled': True}).status_code == 409
    assert client.put('/api/directory/auto-review/config', json={'enabled': True, 'snapshot_id': preview['snapshot_id']}).status_code == 200
    assert client.post('/api/directory/auto-review/execute', json={'snapshot_id': preview['snapshot_id']}).status_code == 200
    assert client.get('/api/directory/auto-review').json()['data']['enabled']
    cid = store.communities()[0]['community_id']
    admission = store.admission(cid)
    assert client.post(f'/api/directory/communities/{cid}/review', json={'revision': admission['revision']}).status_code == 200
    row = client.get('/api/directory/reviews').json()['data']['items'][0]
    assert client.post(f"/api/directory/reviews/{row['id']}/allow-auto-review", json={'revision': row['revision']}).status_code == 200
    preview = client.post('/api/directory/auto-review/preview').json()['data']
    assert preview['counts']['admit'] == 1
    assert client.put('/api/directory/auto-review/config', json={'enabled': False}).status_code == 200


def test_auto_snapshot_is_invalidated_by_target_edit_and_manual_split(tmp_path):
    store, auto = setup(tmp_path)
    add(store)
    add(store, '2', source='amap')
    work = ReviewWorkspace(store, tmp_path)
    row = work.reviews()[0]
    preview = auto.preview(); auto.configure(True, preview['snapshot_id'])
    work.split(row['id'], revision=row['revision'], member_ids=[row['members'][0]['id']])
    with pytest.raises(ValueError, match='变化'):
        auto.execute(preview['snapshot_id'])
    assert auto.preview()['counts']['admit'] == 0


def test_local_collection_default_preview_and_optin_execution(tmp_path, monkeypatch):
    from src.services.directory_collection import collect_names
    store, auto = setup(tmp_path)
    adapters = {'tmsf': lambda *args: iter([
        dict(source='tmsf', source_id='1', name='清河花园', district='滨江', address='滨江区清河路1号', property_type='住宅')])}
    import threading
    report = collect_names(store, ['tmsf'], cancel=threading.Event(), adapters=adapters)
    assert report['auto_review']['counts']['admit'] == 1 and store.communities() == []
    preview = auto.preview(); auto.configure(True, preview['snapshot_id'])
    report = collect_names(store, ['tmsf'], cancel=threading.Event(), adapters=adapters)
    assert report['auto_review']['counts']['applied'] == 1


def test_verified_manual_target_accepts_identity_hints_without_new_residential_claim(tmp_path):
    store, auto = setup(tmp_path)
    cid = store.create('清河花园', district='滨江', address='滨江区清河路1号')['community_id']
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    source = add(store, source='amap')
    with store.db() as db:
        db.execute("UPDATE sources SET cid=NULL,status='pending' WHERE id=?", (source['id'],))
    assert auto.preview()['counts']['merge'] == 1


def test_rule_change_requires_explicit_reenable(tmp_path, monkeypatch):
    store, auto = setup(tmp_path); add(store)
    preview = auto.preview(); auto.configure(True, preview['snapshot_id'])
    monkeypatch.setattr('src.services.community_auto_review.RULE_VERSION', 'new-reviewed-rule')
    assert auto.status()['enabled'] is False
    preview = auto.preview()
    with pytest.raises(ValueError, match='启用'):
        auto.execute(preview['snapshot_id'])


def test_existing_pending_master_admits_without_rebinding_its_members(tmp_path):
    store, auto = setup(tmp_path)
    cid = store.create('清河花园', district='滨江', address='滨江区清河路1号')['community_id']
    source = add(store)
    assert source['community_id'] == cid
    preview = auto.preview(); assert preview['counts']['admit'] == 1
    auto.configure(True, preview['snapshot_id'])
    report = auto.execute(preview['snapshot_id'])
    assert report['counts'].get('applied') == 1
    assert len(store.communities()) == 1 and store.admission(cid)['decision_kind'] == 'automatic'
    assert store.sources()[0] == source
    store.decide_admission(cid, 'review', revision=store.admission(cid)['revision'])
    store.decide_admission(cid, 'allow-auto-review', revision=store.admission(cid)['revision'])
    store.update(cid, name='清河花园', aliases=[], address='滨江区清河路99号')
    assert auto.preview()['counts']['admit'] == 0  # Changed master evidence needs a new human identity judgement.
