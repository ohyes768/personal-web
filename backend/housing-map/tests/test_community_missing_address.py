import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.services.community_registry import CommunityRegistry
from src.services.community_review import ReviewWorkspace
from src.services.community_admission import community_views
from src.services.community_address import valid_address


@pytest.mark.parametrize('address', [None, '', '  ', '暂无', ' 未知 ', '\n暂 无\t', '--'])
def test_placeholder_address_is_not_admitted(tmp_path, address):
    store = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    store.ingest(dict(source='tmsf',source_id='1',name='襄七房',district='滨江',address=address,property_type='住宅'))
    work = ReviewWorkspace(store,tmp_path)
    assert work.reviews()==[]
    row = work.reviews(state='excluded')[0]
    assert row['address_missing'] and '缺少有效地址' in ' '.join(row['reasons'])
    with pytest.raises(ValueError,match='地址'):
        work.decide(row['id'],'admit',revision=row['revision'],name='襄七房',property_type='住宅')


def test_address_update_returns_candidate_to_review_not_admitted(tmp_path):
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    record=dict(source='tmsf',source_id='1',name='花园',district='滨江',address='暂无',property_type='住宅')
    store.ingest(record);work=ReviewWorkspace(store,tmp_path)
    old=work.reviews(state='excluded')[0]
    store.ingest({**record,'address':'滨江区测试路1号'})
    new=work.reviews()[0]
    assert new['id']==old['id'] and new['revision']>old['revision']
    assert work.reviews(state='excluded')==[] and work.summary()['residential']==0


def test_missing_master_address_uses_actual_source_not_coordinates(tmp_path):
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    c=store.create('旧小区',district='滨江',address='暂无')
    store.decide_admission(c['community_id'],'admit',revision=1,property_type='住宅')
    assert community_views(store,tmp_path,coordinates={c['community_id']:{'formatted_address':'杭州市滨江区猜测位置'}})[0]['admission_state']=='excluded'
    source=store.ingest(dict(source='tmsf',source_id='1',name='旧小区',district='滨江',address='滨江区真实路1号',property_type='住宅'))
    store.associate(source['id'],c['community_id'])
    assert community_views(store,tmp_path)[0]['admission_state']=='admitted'


def test_batch_remove_is_atomic_and_recollection_does_not_revive(tmp_path):
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    for sid in ['1','2']:
        store.ingest(dict(source='tmsf',source_id=sid,name='缺地址'+sid,district='滨江',address='未知'))
    work=ReviewWorkspace(store,tmp_path);rows=work.reviews(state='excluded')
    items=[dict(id=r['id'],revision=r['revision']) for r in rows]
    with pytest.raises(ValueError):
        work.remove_excluded([items[0],{**items[1],'revision':999}])
    assert all(r['status']=='pending' for r in store.sources())
    assert work.remove_excluded(items)['removed']==2
    store.ingest(dict(source='tmsf',source_id='1',name='缺地址1',district='滨江',address='未知'))
    assert work.reviews(state='excluded')==[] and work.reviews()==[]
    assert all(r['status']=='ignored' for r in store.sources())


def test_excluded_api_counts_and_batch_action(tmp_path,monkeypatch):
    from src.api import directory_routes
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    store.ingest(dict(source='tmsf',source_id='1',name='襄七房',district='滨江',address='暂无'))
    monkeypatch.setattr(directory_routes,'store',lambda:store)
    monkeypatch.setattr(directory_routes,'DATA_DIR',tmp_path)
    app=FastAPI();app.include_router(directory_routes.router,prefix='/api')
    client=TestClient(app)
    row=client.get('/api/directory/reviews?state=excluded').json()['data']['items'][0]
    summary=client.get('/api/directory/summary?q=襄七房').json()['data']
    assert summary['filtered']==dict(residential=0,pending=0,excluded=1)
    assert client.post('/api/directory/reviews/remove',json={'items':[dict(id=row['id'],revision=row['revision'])]}).json()['data']['removed']==1
    assert client.get('/api/directory/reviews?state=excluded').json()['data']['total']==0


def test_source_loses_address_without_using_stale_group_address(tmp_path):
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    record=dict(source='tmsf',source_id='1',name='花园',district='滨江',address='滨江区测试路1号')
    store.ingest(record);work=ReviewWorkspace(store,tmp_path)
    assert len(work.reviews())==1
    store.ingest({**record,'address':'未知'})
    assert work.reviews()==[] and work.reviews(state='excluded')[0]['address_missing']


def test_addressless_master_removed_with_sources_and_business_mappings(tmp_path):
    from src.services.rental_reference.refresh import load_verified_mappings
    from src.services.auction_history import load_mappings
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    master=store.create('襄七房',district='滨江',address='暂无')
    for site in ('fang','laipai'):
        r=store.ingest(dict(source=site,source_kind='community' if site=='fang' else 'asset',source_id='123',name='襄七房'))
        store.associate(r['id'],master['community_id'])
    assert load_verified_mappings(tmp_path/'rental_community_mappings.json')==[]
    assert load_mappings(tmp_path/'auction_community_mappings.json',store.communities())=={}
    work=ReviewWorkspace(store,tmp_path);row=work.reviews(state='excluded')[0]
    work.remove_excluded([dict(id=row['id'],revision=row['revision'])])
    assert store.communities()==[] and len(store.communities(deleted=True))==1
    assert all(r['status']=='ignored' for r in store.sources())
