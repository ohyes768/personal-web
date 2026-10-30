"""Unified work is grouped and paged by identity, without changing admission."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.services.directory_pending import project, query


def community(cid, **extra):
    return dict(community_id=cid, community_name='同名花园', address='月明路1号', district='滨江',
                admission_state='excluded', workflow_state='pending', qualification='position_pending', **extra)


def rental(cid, reason='needs_selection'):
    return dict(community_id=cid, community_name='同名花园', reason=reason, candidates=[])


def test_groups_identity_not_names_and_preserves_remaining_issues():
    catalog = [community('a'), community('b')]
    auction = dict(id='asset', name='同名花园', district='滨江', reason='未关联', skipped=False)
    rows = project(catalog, [auction], [rental('a')])
    packet = query(rows)
    assert packet['total'] == 3
    assert packet['counts'] == dict(all=3, admission=2, auction=1, rental=1)
    assert len(next(r for r in packet['items'] if r['community_id'] == 'a')['issues']) == 2
    assert query(rows, kind='rental')['total'] == 1
    after = query(project(catalog, [auction], []))
    assert after['total'] == 3
    assert len(next(r for r in after['items'] if r['community_id'] == 'a')['issues']) == 1


def test_filters_before_paging_and_skips_do_not_inflate_default_count():
    catalog = [community(str(i)) for i in range(35)]
    rentals = [rental(str(i)) for i in range(35)] + [rental('skipped', 'skipped'), rental('deferred', 'search_deferred')]
    rows = project(catalog, [], rentals)
    first, second = query(rows), query(rows, page=2)
    assert first['total'] == 35 and len(first['items']) == 30 and len(second['items']) == 5
    assert not ({r['key'] for r in first['items']} & {r['key'] for r in second['items']})
    included = query(rows, include_skipped=True, kind='rental', rental_status='skipped')
    assert included['total'] == 1 and included['default_pending_total'] == 35
    assert query(rows, district='萧山')['total'] == 0
    assert query(rows, q='月明路')['total'] == 35
    assert query(rows, kind='admission', operation='use')['total'] == 0
    assert query(rows, kind='rental', operation='use')['total'] == 35
    assert query(rows, q='不存在', page=99)['page'] == 1


def test_priority_and_unknown_auction_district():
    rows = project([], [dict(id='a', name='房产', reason='未关联')],
                   [rental('m', 'missing'), rental('f', 'search_failed'), rental('s')])
    assert [r['community_id'] for r in query(rows, kind='rental')['items']] == ['s', 'f', 'm']
    assert query(rows, district='滨江')['total'] == 0
    assert query(rows)['total'] == 4


def test_api_gate_validation_and_unqueried_exclusion(tmp_path, monkeypatch):
    from src.api import directory_workflow_routes as api
    from src.services import directory_workflow as flow
    from src.services.community_registry import CommunityRegistry
    from src.services.directory_policy import KEY, VERSION
    from src.services.rental_reference import matching, probe
    registry = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    monkeypatch.setattr(api, 'store', lambda: registry)
    app = FastAPI(); app.include_router(api.router)
    client = TestClient(app)
    assert client.get('/directory/workflow/pending').status_code == 409
    with registry.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    monkeypatch.setattr(flow, 'inventory', lambda *args: [community('idle', workflow_dummy=True)])
    monkeypatch.setattr(flow, 'auction_tasks', lambda *args, **kwargs: [])
    monkeypatch.setattr(matching, 'source_reviews', lambda *args: [rental('idle', 'missing'), rental('missing', 'missing')])
    monkeypatch.setattr(probe, 'read_state', lambda reg, cid: {} if cid == 'idle' else {'stage': 'homepage_not_found'})
    packet = client.get('/directory/workflow/pending').json()['data']
    assert packet['counts'] == dict(all=2, admission=1, auction=0, rental=1)
    summary = client.get('/directory/workflow/summary').json()['data']
    assert summary['unified_pending'] == 2
    assert client.get('/directory/workflow/pending?kind=invalid').status_code == 422
    assert client.get('/directory/workflow/pending?page=0').status_code == 422
    assert client.get('/directory/workflow/pending?rental_status=search_deferred').status_code == 422


def test_real_registry_readonly_queue_and_existing_auction_decisions(tmp_path, monkeypatch):
    from src.api import directory_workflow_routes as api
    from src.services.community_registry import CommunityRegistry, dump
    from src.services.directory_policy import KEY, VERSION
    from src.services.rental_reference.probe import write_state
    from src.services.rental_reference.association import PREFIX
    registry = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    community_row = registry.create('真实目录小区', district='滨江', address='月明路1号')
    cid = community_row['community_id']
    source = registry.ingest(dict(source='tmsf', source_id='1', name='真实目录小区', district='滨江',
                                 address='月明路1号', property_type='住宅', market_state='second_hand', listing_count=5))
    registry.associate(source['id'], cid)
    auction = registry.ingest(dict(source='laipai', source_kind='asset', source_id='a', name='待关联住宅',
                                  district='滨江', address='月明路1号', auction_ids=[]))
    with registry.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    write_state(registry, cid, stage='homepage_not_found')
    monkeypatch.setattr(api, 'store', lambda: registry)
    app = FastAPI(); app.include_router(api.router)
    client = TestClient(app)
    before = registry.path.read_bytes()
    packet = client.get('/directory/workflow/pending').json()['data']
    assert registry.path.read_bytes() == before
    assert packet['counts'] == dict(all=2, admission=0, auction=1, rental=1)
    assert client.get('/directory/workflow/summary').json()['data']['pipeline'] is False
    assert sum(r['community_id'] is None for r in packet['items']) == 1
    admission_before = registry.admission(cid)
    with registry.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (PREFIX+cid, dump(dict(decision='skipped'))))
    packet = client.get('/directory/workflow/pending?include_skipped=true').json()['data']
    assert packet['total'] == 2 and packet['default_pending_total'] == 1
    row = next(r for r in packet['items'] if r['key'] == 'auction:'+auction['id'])
    response = client.post('/directory/workflow/auctions/'+auction['id'], json=dict(
        action='bind', revision=row['issues'][0]['auction']['revision'], community_id=cid))
    assert response.status_code == 200 and response.json()['success']
    assert client.get('/directory/workflow/pending').json()['data']['total'] == 0
    assert registry.admission(cid) == admission_before
    assert client.get('/directory/workflow/pending?include_skipped=true').json()['data']['total'] == 1
