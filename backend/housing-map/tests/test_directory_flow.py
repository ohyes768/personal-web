import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.services.community_registry import CommunityRegistry, dump
from src.services.directory_policy import KEY, VERSION
from src.services.directory_workflow import inventory, synchronize, admitted, auction_tasks, decide_auction
from src.services.directory_migration import preview, apply, rollback
from src.services.directory_position import position_one, PositionJob


def facts(sid='1', name='风雅钱塘', count=3, **extra):
    return dict(source='tmsf',source_id=sid,name=name,district='滨江',address='月明路1076号',
                property_type='住宅',market_state='second_hand',listing_count=count,**extra)


def master(store, record=None):
    record=record or facts()
    c=store.create(record['name'],district=record['district'],address=record['address'])
    s=store.ingest(record);store.associate(s['id'],c['community_id'])
    with store.db() as db:
        a=store.pending_admission();a.update(state='admitted',decision_kind='migration',reason='旧主档用途证据初始化')
        db.execute('UPDATE community_admission SET payload=? WHERE cid=?',(dump(a),c['community_id']))
    return c,s


def activate(store):
    with store.db() as db: db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(KEY,VERSION))


@pytest.fixture
def store(tmp_path): return CommunityRegistry(tmp_path/'community_registry.sqlite3')


@pytest.mark.parametrize('count,state,code',[(0,'excluded','listing_low'),(1,'excluded','listing_low'),
    (2,'excluded','listing_low'),(3,'admitted','eligible'),(None,'excluded','listing_missing')])
def test_tmsf_gate(store,tmp_path,count,state,code):
    master(store,facts(count=count));activate(store);c=inventory(store,tmp_path)[0]
    assert c['admission_state']==state and c['qualification']==code
    assert '旧主档' not in c['exclusion_reason']


@pytest.mark.parametrize('prop,code',[('公寓','type_uncertain'),('其他','type_uncertain'),('写字楼','non_residential'),(None,'type_missing')])
def test_uncertain_and_nonresidential_not_auction_review(store,tmp_path,prop,code):
    r=facts();r['property_type']=prop;master(store,r);activate(store)
    assert inventory(store,tmp_path)[0]['qualification']==code
    assert auction_tasks(store,tmp_path)==[]


def test_fang_cannot_create_or_veto_tmsf_admission(store,tmp_path):
    c,_=master(store);activate(store)
    s=store.ingest(dict(source='fang',source_id='f1',name=c['community_name'],district='滨江',address=c['address'],
        samples=[{'source_listing_id':'a','property_type':'写字楼'}]))
    store.associate(s['id'],c['community_id'])
    assert admitted(store,tmp_path)[0]['community_id']==c['community_id']
    store.create('只有租金证据',district='滨江',address='其他路1号')
    assert len(admitted(store,tmp_path))==1 and len(inventory(store,tmp_path))==1


def test_newhouse_and_missing_position(store,tmp_path):
    r=facts(count=0);r.update(market_state='new_house',project_id='p1');master(store,r);activate(store)
    c=inventory(store,tmp_path)[0]
    assert c['admission_state']=='admitted' and c['map_status']=='missing_coordinates'


def test_manual_exclusion_and_deleted_sources_survive(store,tmp_path):
    c,_=master(store);store.decide_admission(c['community_id'],'exclude',revision=1,reason='人工保留排除')
    activate(store);assert synchronize(store,tmp_path)==0
    assert inventory(store,tmp_path)[0]['exclusion_reason']=='人工保留排除'
    store.delete(c['community_id']);assert inventory(store,tmp_path)==[]
    assert synchronize(store,tmp_path)==0 and store.sources()[0]['status']=='ignored'


def test_materialize_complete_only_no_duplicates_or_rejected_identity(store,tmp_path):
    activate(store);s=store.ingest(facts());assert synchronize(store,tmp_path)==1
    assert synchronize(store,tmp_path)==0 and len(admitted(store,tmp_path))==1
    store.ingest(facts('2','待补花园',count=None));assert synchronize(store,tmp_path)==0
    assert any(c['facts_state']=='incomplete' for c in inventory(store,tmp_path))
    store.unlink(s['id']);assert synchronize(store,tmp_path)==0 and len(store.communities())==1


def test_qualification_recovers_without_rewriting_history(store,tmp_path):
    c,_=master(store,facts(count=1));activate(store);before=store.admission(c['community_id'])
    assert not admitted(store,tmp_path)
    store.ingest(facts(count=3));assert len(admitted(store,tmp_path))==1
    assert store.admission(c['community_id'])==before


class Client:
    def __init__(self,callback=None,count=1): self.callback,self.count,self.calls=callback,count,0
    def search_name(self,*_):
        self.calls+=1
        if self.callback: self.callback()
        return [dict(id='B1',name='风雅钱塘',adname='滨江区',address='月明路1076号',
            type='商务住宅;住宅区',typecode='120302',location='120.20749,30.20226')],self.count
    def close(self): pass


def test_position_independent_and_preserves_actual_address(store,tmp_path):
    c,_=master(store);activate(store);client=Client()
    assert position_one(store,tmp_path,c['community_id'],client)=='updated'
    saved=store.communities()[0]
    assert saved['address']=='月明路1076号' and saved['coordinate_evidence']['source_id']=='B1'
    assert position_one(store,tmp_path,c['community_id'],client)=='skipped' and client.calls==1


@pytest.mark.parametrize('kind',['edit','exclude','delete','cancel'])
def test_position_stale_or_cancelled_never_publishes(store,tmp_path,kind):
    c,_=master(store);activate(store)
    def change():
        if kind=='edit': store.update(c['community_id'],name=c['community_name'],aliases=[],address='手工地址')
        if kind=='exclude': store.decide_admission(c['community_id'],'exclude',revision=1,reason='人工排除')
        if kind=='delete': store.delete(c['community_id'])
    with pytest.raises((ValueError,InterruptedError)):
        position_one(store,tmp_path,c['community_id'],Client(change),cancelled=lambda:kind=='cancel')
    assert 'longitude' not in store.communities(deleted=kind=='delete')[0]


def test_position_budget_ambiguity_restart(store,tmp_path):
    c,_=master(store);activate(store)
    with pytest.raises(ValueError,match='唯一'): position_one(store,tmp_path,c['community_id'],Client(count=30))
    # Ambiguous results await manual confirmation; budget applies to pending targets.
    master(store,facts('budget-target','A待补全'))
    job=PositionJob(store);job.state=dict(running=True,phase='running',total=0,processed=0,updated=0,skipped=0,review=0,not_found=0,failed=0,skipped_by_state={},errors=[])
    job._run(client=Client(),delay=0,budget=0)
    assert job.snapshot()['phase']=='partial_failed' and job.snapshot()['processed']==0
    job.state.update(running=True,phase='running');job._save()
    assert PositionJob(store).snapshot()['phase']=='interrupted'


def auction(store):
    return store.ingest(dict(source='laipai',source_kind='asset',source_id='a1',name='未知花园',
        district='滨江',address='其他路1号',auction_ids=['10']))


def test_auction_queue_bind_skip_reopen_stale_revision(store,tmp_path):
    c,_=master(store);activate(store);store.ingest(facts('2','资料缺失',count=None));auction(store)
    rows=auction_tasks(store,tmp_path);assert len(rows)==1;r=rows[0]
    decide_auction(store,tmp_path,r['id'],revision=r['revision'],action='skip');assert auction_tasks(store,tmp_path)==[]
    assert auction_tasks(store,tmp_path,include_skipped=True)[0]['skipped']
    decide_auction(store,tmp_path,r['id'],revision=r['revision'],action='reopen')
    decide_auction(store,tmp_path,r['id'],revision=r['revision'],action='bind',community_id=c['community_id'])
    assert auction_tasks(store,tmp_path)==[]
    with pytest.raises(ValueError,match='变化'):
        decide_auction(store,tmp_path,r['id'],revision=r['revision'],action='skip')


def test_bind_rejects_now_excluded_target(store,tmp_path):
    c,_=master(store);activate(store);auction(store);r=auction_tasks(store,tmp_path)[0];store.ingest(facts(count=1))
    with pytest.raises(ValueError,match='已收录'):
        decide_auction(store,tmp_path,r['id'],revision=r['revision'],action='bind',community_id=c['community_id'])


def test_preview_readonly_backup_idempotence_rollback(store,tmp_path):
    c,_=master(store,facts(count=1));before=store.path.read_bytes();events=store.events(c['community_id'])
    plan=preview(tmp_path)
    assert before==store.path.read_bytes() and store.events(c['community_id'])==events
    assert plan['changes'][0]['after']=='excluded' and plan['totals']['admitted']==0
    backup=tmp_path.parent/(tmp_path.name+'-backup');report=apply(tmp_path,plan,backup,maintenance=True)
    assert (backup/'community_registry.sqlite3').exists() and report['created']==0
    assert store.admission(c['community_id'])['reason']=='旧主档用途证据初始化'
    assert '旧主档' not in inventory(store,tmp_path)[0]['exclusion_reason']
    assert apply(tmp_path,preview(tmp_path),backup,maintenance=True)=={'already_applied':True}
    assert rollback(tmp_path,backup,maintenance=True)=={'rolled_back':True}
    with store.db() as db: assert db.execute('SELECT 1 FROM meta WHERE key=?',(KEY,)).fetchone() is None


def test_preview_materializes_only_in_memory(store,tmp_path):
    store.ingest(facts());plan=preview(tmp_path)
    assert store.communities()==[] and plan['totals']['admitted']==1
    backup=tmp_path.parent/(tmp_path.name+'-backup');apply(tmp_path,plan,backup,maintenance=True)
    assert admitted(store,tmp_path)[0]['community_id']==plan['changes'][0]['community_id']


def test_stale_plan_and_postmigration_writes_refuse_rollback(store,tmp_path):
    master(store);plan=preview(tmp_path);store.ingest(facts(count=1));backup=tmp_path.parent/(tmp_path.name+'-backup')
    with pytest.raises(ValueError,match='快照'): apply(tmp_path,plan,backup,maintenance=True)
    assert not backup.exists()
    apply(tmp_path,preview(tmp_path),backup,maintenance=True);store.ingest(facts(count=3))
    with pytest.raises(ValueError,match='新数据'): rollback(tmp_path,backup,maintenance=True)


def test_api_migration_gate_catalog_and_auction_counts(store,tmp_path,monkeypatch):
    from src.api import directory_routes
    monkeypatch.setattr(directory_routes,'store',lambda:store);monkeypatch.setattr(directory_routes,'DATA_DIR',tmp_path)
    app=FastAPI();app.include_router(directory_routes.router,prefix='/api');client=TestClient(app)
    assert client.get('/api/directory/workflow/summary').json()['data']['active'] is False
    assert client.get('/api/directory/workflow/catalog').status_code==409
    master(store);activate(store);store.ingest(facts('2','低挂牌花园',count=1));auction(store)
    data=client.get('/api/directory/workflow/summary').json()['data']
    assert data['admitted']==1 and data['excluded']==1 and data['auction_pending']==1
    assert client.get('/api/directory/workflow/catalog?state=excluded').json()['data']['items'][0]['facts_state']=='complete'
    assert client.get('/api/directory/workflow/catalog?page=0').status_code==422


def test_source_only_human_exclusion_keeps_reason_and_never_materializes(store,tmp_path):
    from src.services.community_review import ReviewWorkspace
    store.ingest(facts())
    work=ReviewWorkspace(store,tmp_path);row=work.reviews()[0]
    work.decide(row['id'],'exclude',revision=row['revision'],reason='人工排除重复小区')
    activate(store)
    assert synchronize(store,tmp_path)==0
    assert inventory(store,tmp_path)[0]['exclusion_reason']=='人工排除重复小区'


def test_migration_reports_non_tmsf_master_disappearing_from_map(store,tmp_path):
    c=store.create('仅旧租金住宅',district='滨江',address='测试路1号')
    with store.db() as db:
        a=store.pending_admission();a.update(state='admitted',decision_kind='manual',property_type='住宅')
        db.execute('UPDATE community_admission SET payload=? WHERE cid=?',(dump(a),c['community_id']))
    plan=preview(tmp_path)
    row=next(r for r in plan['changes'] if r['community_id']==c['community_id'])
    assert row['before']=='admitted' and row['after']=='excluded'
    assert row['qualification']=='missing_tmsf' and row['manual_conflict'] and not row['catalog_visible']


def test_position_skip_needs_no_key_or_network(store,tmp_path,monkeypatch):
    from src.services import directory_position
    c,_=master(store);activate(store)
    position_one(store,tmp_path,c['community_id'],Client())
    def unexpected(): raise AssertionError('valid position must not initialize an upstream client')
    monkeypatch.setattr(directory_position,'AmapClient',unexpected)
    job=PositionJob(store);job.state=dict(running=True,phase='running',total=0,processed=0,updated=0,skipped=0,review=0,not_found=0,failed=0,skipped_by_state={},errors=[])
    job._run(delay=0)
    assert job.snapshot()['phase']=='succeeded' and job.snapshot()['skipped']==1


def test_active_rental_targets_match_admission_and_drop_after_gate_change(store,tmp_path):
    from src.services.rental_reference.association import eligible_communities
    from src.services.rental_reference.refresh import load_verified_mappings
    c,_=master(store);activate(store)
    s=store.ingest(dict(source='fang',source_id='f1',name=c['community_name'],district='滨江',address=c['address']))
    store.associate(s['id'],c['community_id'])
    assert [r['community_id'] for r in eligible_communities(store)[0]]==[c['community_id']]
    assert load_verified_mappings(tmp_path/'rental_community_mappings.json')==[('f1',c['community_id'])]
    store.ingest(facts(count=1))
    assert eligible_communities(store)[0]==[]
    assert load_verified_mappings(tmp_path/'rental_community_mappings.json')==[]


def test_active_old_auto_review_cannot_be_enabled_or_executed(store,tmp_path):
    from src.services.community_auto_review import AutoReview
    master(store);activate(store);auto=AutoReview(store,tmp_path)
    with pytest.raises(ValueError,match='停用'): auto.configure(True,'0'*64)
    with pytest.raises(ValueError,match='停用'): auto.execute('0'*64)


def test_collection_auto_classifies_without_old_preview_enablement(store,tmp_path):
    from src.services.directory_collection import collect_names
    activate(store)
    report=collect_names(store,['tmsf'],adapters={'tmsf':lambda *_ ,**kwargs: iter([facts()])})
    assert report['phase']=='succeeded'
    assert len(admitted(store,tmp_path))==1
    assert report['auto_review']['mode']=='tmsf_directory'


def test_same_name_different_district_is_not_a_global_name_blacklist(store,tmp_path):
    store.create('风雅钱塘',district='萧山',address='其他路1号')
    activate(store);store.ingest(facts())
    assert synchronize(store,tmp_path)==1
    assert len(admitted(store,tmp_path))==1


@pytest.mark.parametrize('count,state', [(0, 'excluded'), (2, 'excluded'), (3, 'admitted')])
def test_sold_out_legacy_project_reclassified_in_active_directory(store, tmp_path, count, state):
    record = facts(count=count)
    record.update(market_state='new_house', project_id='812', project_sale_status='售完')
    master(store, record)
    activate(store)
    item = inventory(store, tmp_path)[0]
    assert item['market_state'] == 'second_hand'
    assert item['admission_state'] == state
    if state == 'excluded':
        assert item['qualification'] == 'listing_low'
        assert admitted(store, tmp_path) == []
