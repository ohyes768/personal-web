import json
from types import SimpleNamespace

import pytest

from src.services.community_registry import CommunityRegistry
from src.services.community_admission import community_views
from src.services.community_enrichment import enrich_source
from src.services.residential_classifier import classify_sources
from src.services.tmsf_property_type import (parse_project_index, find_project, fetch_project_facts,
                                            fetch_property_facts, PROJECT_INDEX_URL)

NAME = '万科朗拾滨屿府'
ADDRESS = '信诚南路与博研弄交叉口西侧(硅谷小学北)'
PROJECT = dict(propertyid=2313460053, siteid=33, propertyname='万科朗拾滨屿府(朗拾滨屿府)', districtname='滨江', propertystateid=4)
INDEX = 'var data_auto = ' + json.dumps([PROJECT], ensure_ascii=False) + '; var other = []'
# Reduced fixture using fields inspected in the actual public newhouse DOM.
NEW_PAGE = f'''<div class="house_float_name_title">朗拾滨屿府</div>
<a id="districtname">滨江楼盘</a><div class="house_float_name_tips_grey">住宅</div>
<div class="house_float_name_tips_grey999">售完</div>
<div class="house_information_list_mian_left">楼盘地址</div>
<div class="house_information_list_mian_right house_information_list_mian_dw">{ADDRESS}</div>'''
COMMUNITY_PAGE = f'<input id="communityname_auto" value="{NAME}"><input id="managetypename_auto" value="住宅">'


def client(community=COMMUNITY_PAGE, project=NEW_PAGE):
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        if url == PROJECT_INDEX_URL:
            return INDEX
        return project if '/newhouse/' in url else community
    return SimpleNamespace(fetch_text=fetch), calls


def test_newhouse_fallback_resolves_independent_project_id():
    upstream, calls = client(community='<html>无二手房详情</html>')
    facts = fetch_property_facts(upstream, '3017629894', [NAME])
    assert facts['property_type'] == '住宅'
    assert facts['project_id'] == '2313460053'
    assert facts['address'] == ADDRESS and facts['project_sale_status'] == '售完'
    assert facts['market_state'] == 'new_house'
    assert calls[-1].endswith('property_33_2313460053_infoUpgrade.htm')
    assert all('property_33_3017629894' not in url for url in calls)


def test_project_index_preserves_phases_and_rejects_duplicate_identity():
    assert find_project(parse_project_index(INDEX), [NAME], '滨江')['propertyid'] == 2313460053
    with pytest.raises(ValueError, match='歧义'):
        find_project([PROJECT, {**PROJECT, 'propertyid': 2}], [NAME], '滨江')
    with pytest.raises(ValueError):
        find_project([PROJECT], [NAME + '二期'], '滨江')
    with pytest.raises(ValueError):
        find_project([PROJECT], [NAME], '萧山')


@pytest.mark.parametrize('page', ['<html>请验证</html>', NEW_PAGE.replace('滨江楼盘', '上城楼盘'),
    NEW_PAGE.replace('朗拾滨屿府</div>', '朗拾滨屿府二期</div>')])
def test_project_challenge_wrong_district_or_phase_stays_unverified(page):
    upstream, _ = client(project=page)
    with pytest.raises(ValueError):
        fetch_project_facts(upstream, [NAME], '滨江')


def test_failed_attempt_preserves_type_but_conflict_requires_review():
    source = dict(source='tmsf', source_id='1', property_type='住宅', property_type_error='请求失败')
    assert classify_sources([source]) == 'residential'
    assert classify_sources([{**source, 'property_type': None}]) == 'pending'
    assert classify_sources([{**source, 'property_type_conflict': True}]) == 'pending'
    assert classify_sources([source, dict(source='fang', samples=[{'property_type': '写字楼'}])]) == 'pending'


def seed(tmp_path, *, history=True):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    cid = store.create(NAME, district='滨江', address='', community_id='local-new')['community_id']
    source = store.ingest(dict(source='tmsf', source_id='3017629894', name=NAME, district='滨江', listing_count=3))
    store.associate(source['id'], cid)
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    if history:
        (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({'3017629894': dict(
            name=NAME, longitude=120.176013, latitude=30.162944, formatted_address='浙江省杭州市滨江区' + NAME)}))
        (tmp_path / 'price_snapshots.jsonl').write_text(json.dumps(dict(community_id='3017629894',
            community_name=NAME, source_url='https://www.tmsf.com/esf/xq_indexnew_3017629894.htm',
            raw_payload=dict(community=dict(address=ADDRESS)))))
    return store, source, cid


def test_historical_source_id_repairs_local_master_without_changing_manual_decision(tmp_path):
    store, source, cid = seed(tmp_path)
    upstream, _ = client()
    admission = store.admission(cid)
    report = enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert not report['errors']
    view = community_views(store, tmp_path)[0]
    assert view['map_status'] == 'displayed' and view['market_state'] == 'new_house'
    assert view['longitude'] == 120.176013 and view['address'] == ADDRESS
    assert store.admission(cid) == admission and store.sources()[0]['community_id'] == cid
    assert store.sources()[0]['coordinate_evidence']['source_id'] == '3017629894'


def test_failed_project_preserves_history_and_failed_attempt_is_visible(tmp_path):
    store, source, _ = seed(tmp_path)
    store.ingest(dict(source='tmsf', source_id='3017629894', name=NAME, property_type='住宅'))
    upstream, _ = client(community='<html>blocked</html>', project='<html>blocked</html>')
    report = enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert report['errors'] and store.sources()[0]['property_type_error']
    view = community_views(store, tmp_path)[0]
    assert view['residential_state'] == 'residential' and view['market_state'] == 'new_house'
    assert view['map_status'] == 'displayed'


def test_wrong_historical_name_and_sale_office_never_supply_coordinates(tmp_path):
    store, source, _ = seed(tmp_path)
    (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({'3017629894': dict(
        name=NAME + '二期', longitude=120.176013, latitude=30.162944, formatted_address='滨江区')}))
    upstream, _ = client()
    amap = SimpleNamespace(search_name=lambda *_: ([dict(id='p', name=NAME+'售楼处', adname='滨江区',
        typecode='120300', location='120.176013,30.162944', address=ADDRESS)], 1))
    report = enrich_source(store, tmp_path, source['id'], tmsf_client=upstream, amap_client=amap)
    assert report['errors']
    assert community_views(store, tmp_path)[0]['map_status'] == 'missing_coordinates'


def test_source_change_during_request_prevents_publication(tmp_path):
    store, source, _ = seed(tmp_path)
    upstream, _ = client()
    fetch = upstream.fetch_text
    def changed(url, timeout):
        store.ignore_source(source['id'])
        return fetch(url, timeout)
    upstream.fetch_text = changed
    with pytest.raises(ValueError, match='变化'):
        enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert store.sources()[0]['status'] == 'ignored'
    assert 'project_id' not in store.sources()[0]


def test_admitted_project_without_coordinates_remains_in_directory(tmp_path):
    store, source, cid = seed(tmp_path, history=False)
    upstream, _ = client()
    amap = SimpleNamespace(search_name=lambda *_: ([], 0))
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream, amap_client=amap)
    view = community_views(store, tmp_path)[0]
    assert view['admission_state'] == 'admitted' and view['map_status'] == 'missing_coordinates'
    assert view['market_state'] == 'new_house'


def test_position_conflicts_never_choose_first_associated_source(tmp_path):
    store, source, cid = seed(tmp_path, history=False)
    store.update(cid, name=NAME, aliases=[], address='滨江区信诚南路')
    for sid, lng in [('a', 120.176013), ('b', 120.18)]:
        r = store.ingest(dict(source='amap', source_id=sid, name=NAME, district='滨江',
            longitude=lng, latitude=30.162944, coordinate_system='gcj02'))
        store.associate(r['id'], cid)
    assert community_views(store, tmp_path)[0]['map_status'] == 'check_coordinates'


def test_enrichment_corrects_only_marked_legacy_address(tmp_path):
    store, source, cid = seed(tmp_path)
    old = '浙江省杭州市滨江区' + NAME
    with store.db() as db:
        row = db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()
        value = json.loads(row['payload'])
        value.update(address=old, geographic_address=old, address_origin='legacy_geocoder')
        db.execute('UPDATE communities SET payload=? WHERE id=?', (json.dumps(value), cid))
    upstream, _ = client()
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert store.communities()[0]['address'] == ADDRESS
    store.update(cid, name=NAME, aliases=[], address='滨江区人工核实地址')
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert store.communities()[0]['address'] == '滨江区人工核实地址'


def test_coordinates_loader_uses_associated_source_position(tmp_path, monkeypatch):
    from src.services import data_loader
    store, source, cid = seed(tmp_path)
    upstream, _ = client()
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    assert data_loader.load_coordinates()[cid]['longitude'] == 120.176013
    assert data_loader.load_display_communities()[0]['community_id'] == cid


def test_newhouse_price_never_leaks_into_second_hand_snapshot(tmp_path):
    from src.services.data_loader import load_price_snapshots
    path = tmp_path / 'price_snapshots.jsonl'
    rows = [dict(community_id='1', avg_price=100, price_type='listing_avg', listing_count=1,
                 market_state='new_house'),
            dict(community_id='2', avg_price=200, price_type='listing_avg', listing_count=1,
                 source_url='https://www.tmsf.com/newhouse/property_33_2_infoUpgrade.htm'),
            dict(community_id='3', avg_price=300, price_type='listing_avg', listing_count=1)]
    path.write_text('\n'.join(json.dumps(r) for r in rows))
    assert set(load_price_snapshots(path)) == {'3'}


def test_enrichment_api_exposes_partial_failure_without_admission_mutation(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import directory_routes
    from src.services import community_enrichment
    store, source, cid = seed(tmp_path)
    admission = store.admission(cid)
    upstream, _ = client(project='<html>请验证</html>')
    original = enrich_source
    monkeypatch.setattr(community_enrichment, 'enrich_source', lambda store, data, rid: original(
        store, data, rid, tmsf_client=upstream))
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(directory_routes, 'DATA_DIR', tmp_path)
    app = FastAPI(); app.include_router(directory_routes.router, prefix='/api')
    api = TestClient(app)
    response = api.post('/api/directory/sources/' + source['id'] + '/enrich')
    assert response.status_code == 200 and response.json()['data']['errors']
    assert store.admission(cid) == admission
    store.ignore_source(source['id'])
    assert api.post('/api/directory/sources/' + source['id'] + '/enrich').status_code == 409


def test_newhouse_zero_esf_listings_keeps_identity_on_collection(tmp_path, monkeypatch):
    import threading
    from src.services import directory_collection, tmsf_fetcher
    from scripts import fetch_tmsf_binjiang_communities as listing
    upstream, calls = client(community=COMMUNITY_PAGE + '<div>挂牌房源数<span class="bold">0 套</span></div>')
    upstream.close = lambda: None
    monkeypatch.setattr(tmsf_fetcher, 'TmsfClient', lambda: upstream)
    monkeypatch.setattr(directory_collection, 'pause', lambda _: None)
    monkeypatch.setattr(listing, 'fetch_binjiang_communities', lambda: [SimpleNamespace(
        community_id='3017629894', community_name=NAME, community_alias=NAME,
        district='滨江', subdistrict='浦沿', source_url='https://www.tmsf.com/list.js')])
    rows = list(directory_collection.tmsf_names(threading.Event(), lambda *_: False))
    assert rows[-1]['market_state'] == 'new_house' and rows[-1]['listing_count'] == 0
    assert rows[-1]['project_id'] == '2313460053' and rows[-1]['project_sale_status'] == '售完'
    from src.services.community_listing import listing_gate
    assert listing_gate([rows[-1]])[0] is None


def test_enrichment_retains_confirmed_newhouse_when_index_temporarily_fails(tmp_path):
    store, source, _ = seed(tmp_path)
    upstream, _ = client()
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    def no_index(url, timeout):
        return '<html>blocked</html>' if url == PROJECT_INDEX_URL else COMMUNITY_PAGE
    upstream.fetch_text = no_index
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert store.sources()[0]['market_state'] == 'new_house'
    assert store.sources()[0]['market_state_error']


def test_automatic_newhouse_admission_keeps_verified_street_district_for_map(tmp_path):
    from src.services.community_auto_review import AutoReview
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    # A verified detail street and its separately parsed district are real address evidence.
    store.ingest(dict(source='tmsf', source_id='3017629894', name=NAME, district='滨江',
        address=ADDRESS, address_district='滨江', property_type='住宅', market_state='new_house',
        listing_count=0, longitude=120.176013, latitude=30.162944, coordinate_system='gcj02'))
    auto = AutoReview(store, tmp_path)
    preview = auto.preview()
    assert preview['counts']['admit'] == 1
    auto.configure(True, preview['snapshot_id']); auto.execute(preview['snapshot_id'])
    assert community_views(store, tmp_path)[0]['map_status'] == 'displayed'


def test_first_failed_refresh_retains_legacy_residential_fact(tmp_path):
    store, source, _ = seed(tmp_path)
    (tmp_path / 'property_types.json').write_text(json.dumps({'3017629894': dict(
        property_type='住宅', url='https://www.tmsf.com/esf/xq_indexnew_3017629894.htm')}))
    upstream, _ = client(community='<html>验证</html>', project='<html>验证</html>')
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert store.sources()[0]['property_type'] == '住宅'
    assert store.sources()[0]['property_type_error']
    assert community_views(store, tmp_path)[0]['residential_state'] == 'residential'


def test_conflicting_newhouse_use_and_retained_community_fact_requires_review(tmp_path):
    store, source, _ = seed(tmp_path)
    store.ingest(dict(source='tmsf', source_id='3017629894', name=NAME, property_type='住宅'))
    upstream, _ = client(community='<html>验证</html>', project=NEW_PAGE.replace('>住宅</div>', '>写字楼</div>'))
    enrich_source(store, tmp_path, source['id'], tmsf_client=upstream)
    assert store.sources()[0]['project_property_type'] == '写字楼'
    assert store.sources()[0]['property_type'] == '住宅'
    assert store.sources()[0]['property_type_conflict']
    assert community_views(store, tmp_path)[0]['residential_state'] == 'pending'
