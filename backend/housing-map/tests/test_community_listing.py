import pytest
from src.services.community_registry import CommunityRegistry
from src.services.community_review import ReviewWorkspace
from src.services.community_admission import community_views
from src.services.community_listing import listing_gate
from src.services.community_auto_review import AutoReview
from src.services.tmsf_property_type import fetch_property_facts as fetch_community_facts
from types import SimpleNamespace


def record(count=3, **extra):
    return dict(source='tmsf', source_id='1', name='测试花园', district='滨江',
                address='滨江区测试路1号', property_type='住宅', market_state='second_hand',
                listing_count=count, **extra)


@pytest.mark.parametrize('count', [0, 1, 2])
def test_low_counts_excluded_and_cannot_admit(tmp_path, count):
    store = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    store.ingest(record(count))
    work = ReviewWorkspace(store,tmp_path)
    assert work.reviews() == []
    row = work.reviews(state='excluded')[0]
    assert str(count)+' 套' in ' '.join(row['reasons'])
    assert work.summary()['excluded'] == 1
    assert AutoReview(store,tmp_path).preview()['items'][0]['action'] == 'exclude'
    with pytest.raises(ValueError, match='少于'):
        work.decide(row['id'],'admit',revision=row['revision'],name=row['name'],property_type='住宅')
    assert not store.communities()


@pytest.mark.parametrize('count', [None, -1, True, '2'])
def test_unknown_count_pending_not_zero(tmp_path,count):
    store = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    store.ingest(record(count))
    work = ReviewWorkspace(store,tmp_path)
    assert len(work.reviews()) == 1 and work.reviews(state='excluded') == []
    assert AutoReview(store,tmp_path).preview()['items'][0]['action'] == 'pending'


def test_three_admits_then_lower_count_withdraws_without_deleting(tmp_path):
    store = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    store.ingest(record())
    work=ReviewWorkspace(store,tmp_path);row=work.reviews()[0]
    work.decide(row['id'],'admit',revision=row['revision'],name=row['name'],property_type='住宅')
    cid=store.communities()[0]['community_id']
    store.ingest(record(2))
    view=community_views(store,tmp_path)[0]
    assert view['admission_state']=='excluded' and view['admission']['state']=='admitted'
    assert view['map_status']=='not_admitted'
    assert store.sources()[0]['status']=='matched'
    with pytest.raises(ValueError,match='少于'):
        store.decide_admission(cid,'admit',revision=store.admission(cid)['revision'],property_type='住宅')
    assert work.reviews(state='excluded')[0]['existing_cid']==cid
    store.ingest(record(3))
    assert community_views(store,tmp_path)[0]['admission_state']=='admitted'


def test_new_house_and_failed_count():
    assert listing_gate([{**record(0),'market_state':'new_house'}])[0] is None
    assert listing_gate([record(0, listing_count_error='网络错误')])[0]=='pending'
    assert listing_gate([record(2),{**record(4),'source_id':'2'}])[0] is None


def test_real_page_fact_count_zero_and_missing():
    html='<input id="communityname_auto" value="测试花园"><input id="managetypename_auto" value="住宅"><div>挂牌房源数<span class="bold">0 套</span></div>'
    result=fetch_community_facts(SimpleNamespace(fetch_text=lambda *_:html),'1',['测试花园'])
    assert result['listing_count']==0 and result['market_state']=='second_hand'
    result=fetch_community_facts(SimpleNamespace(fetch_text=lambda *_:html.split('<div>')[0]),'1',['测试花园'])
    assert result['listing_count'] is None


def test_api_lists_reason_and_rejects_admit(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import directory_routes
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    store.ingest(record(2))
    monkeypatch.setattr(directory_routes,'store',lambda:store)
    monkeypatch.setattr(directory_routes,'DATA_DIR',tmp_path)
    app=FastAPI();app.include_router(directory_routes.router,prefix='/api')
    client=TestClient(app)
    row=client.get('/api/directory/reviews?state=excluded').json()['data']['items'][0]
    assert '少于 3 套' in ' '.join(row['reasons'])
    assert client.get('/api/directory/summary').json()['data']['filtered']['excluded']==1
    response=client.post('/api/directory/reviews/'+row['id']+'/decision',json=dict(
        action='admit',revision=row['revision'],name=row['name'],property_type='住宅'))
    assert response.status_code==409


def test_unknown_count_withdraws_then_success_recovers(tmp_path):
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    store.ingest(record(3));work=ReviewWorkspace(store,tmp_path);row=work.reviews()[0]
    work.decide(row['id'],'admit',revision=row['revision'],name=row['name'],property_type='住宅')
    store.ingest(record(3,listing_count_error='请求失败'))
    assert community_views(store,tmp_path)[0]['admission_state']=='pending'
    store.ingest(record(3,listing_count_error=None))
    assert community_views(store,tmp_path)[0]['admission_state']=='admitted'


def test_legacy_master_count_and_manual_exclusion_remain(tmp_path):
    store=CommunityRegistry(tmp_path/'community_registry.sqlite3')
    c=store.create('测试花园',district='滨江',address='滨江区测试路1号')
    # Legacy masters have counts while imported source payloads do not.
    import json
    with store.db() as db:
        row=db.execute('SELECT payload FROM communities WHERE id=?',(c['community_id'],)).fetchone()
        value=json.loads(row[0]);value['listing_count']=0
        db.execute('UPDATE communities SET payload=? WHERE id=?',(json.dumps(value),c['community_id']))
    source=store.ingest(dict(source='tmsf',source_id='1',name='测试花园',property_type='住宅'))
    store.associate(source['id'],c['community_id'])
    assert community_views(store,tmp_path)[0]['admission_state']=='excluded'
    store.decide_admission(c['community_id'],'exclude',revision=1,reason='人工不收录')
    store.ingest(record(3))
    assert community_views(store,tmp_path)[0]['admission_state']=='excluded'
