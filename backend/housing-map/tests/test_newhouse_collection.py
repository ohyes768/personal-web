"""新房独立发现与 project 来源身份隔离。Q1：截断地址永不充当完整地址。"""
import json
from types import SimpleNamespace

import pytest

from src.services.community_registry import CommunityRegistry
from src.services.community_admission import community_views
from src.services.community_enrichment import enrich_source, historical_evidence
from src.services.community_listing import listing_gate
from src.services.directory_collection import collect_names
from src.services.directory_workflow import inventory, materialize
from src.services.tmsf_property_type import fetch_project_facts_by_id, PROJECT_INDEX_URL

ADDRESS = '杭州市滨江区江晖路2030号'
PID = '2313460053'
SELLING = dict(propertyid=int(PID), siteid=33, propertyname='万科春来晴翠园(春来晴翠园)', districtname='滨江', propertystateid=2)
WAIT = dict(propertyid=3000000002, siteid=33, propertyname='泊玺骏庐', districtname='滨江', propertystateid=5)
SOLD = dict(propertyid=3000000003, siteid=33, propertyname='月澜雅颂里', districtname='滨江', propertystateid=4)
XIAOSHAN = dict(propertyid=3000000004, siteid=10, propertyname='萧然府', districtname='萧山', propertystateid=2)
INDEX = 'var data_auto = ' + json.dumps([SELLING, WAIT, SOLD, XIAOSHAN], ensure_ascii=False)


def page(name='春来晴翠园', prop='住宅', status='在售', address=ADDRESS, truncate=False):
    """Reduced fixture from the inspected newhouse DOM: use/status live in the
    price/residence and greenlight blocks, not only the legacy grey classes."""
    return (f'<div class="house_float_name_title">{name}</div>'
            '<a id="districtname">滨江楼盘</a>'
            '<div class="house_float_price_name">物业类型</div>'
            f'<div class="house_information_price_residence">{prop}</div>'
            f'<div class="house_float_name_tips_greenlight">{status}</div>'
            '<div class="house_information_list_mian_left">楼盘地址</div>'
            f'<div class="house_information_list_mian_right">{address}{"…" if truncate else ""}</div>')


def client(projects=None, index=INDEX, community='<html>无二手房详情</html>'):
    pages = {p['propertyid']: page(p['propertyname'].split('(')[-1].rstrip(')'),
                                   status='待售' if p is WAIT else '在售')
             for p in (projects if projects is not None else [SELLING, WAIT])}
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        if url == PROJECT_INDEX_URL:
            if index is None:
                raise TimeoutError('upstream timeout')
            return index
        if '/newhouse/property_' in url:
            pid = int(url.split('_')[-2])
            if pid not in pages:
                raise ValueError('unexpected project page: ' + url)
            return pages[pid]
        return community

    return SimpleNamespace(fetch_text=fetch, close=lambda: None), calls


def listing_row(cid, name, alias=''):
    return SimpleNamespace(community_id=cid, community_name=name, community_alias=alias,
                           district='滨江', subdistrict='', source_url='https://www.tmsf.com/esf')


def patch(monkeypatch, upstream, communities):
    import scripts.fetch_tmsf_binjiang_communities as listing
    from src.services import tmsf_fetcher, directory_collection
    monkeypatch.setattr(listing, 'fetch_binjiang_communities', lambda: communities)
    monkeypatch.setattr(tmsf_fetcher, 'TmsfClient', lambda *a, **k: upstream)
    monkeypatch.setattr(directory_collection, 'pause', lambda cancel: None)


def project_rows(store):
    return {r['source_id']: r for r in store.sources() if r.get('source_kind') == 'project'}


def test_newhouse_discovery_saves_candidates_without_esf_entry(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    upstream, calls = client()
    patch(monkeypatch, upstream, [listing_row('9999999999', '白金海岸')])
    report = collect_names(store, ['tmsf'])
    rows = project_rows(store)
    assert set(rows) == {PID, str(WAIT['propertyid'])}, '售完与外区项目不入候选'
    row = rows[PID]
    assert row['name'] == '春来晴翠园' and row['project_sale_status'] == '在售'
    assert row['market_state'] == 'new_house' and row['property_type'] == '住宅'
    assert row['address'] == ADDRESS and row['address_origin'] == 'source_detail'
    assert row['source_url'].endswith(f'property_33_{PID}_infoUpgrade.htm')
    assert all('/esf/xq_indexnew_' + PID not in u for u in calls), '新房来源不得拼接二手房 URL'
    assert report['phase'] == 'partial_failed' and report['new'] == 3
    assert all(e.get('stage') != 'newhouse_index' for e in report['errors'])


def test_detail_failure_keeps_name_candidate_with_coded_error(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    upstream, _ = client(projects=[SELLING])
    upstream.fetch_text = lambda url, timeout: (
        (_ for _ in ()).throw(RuntimeError('HTTP 500')) if '/newhouse/property_' in url
        else INDEX if url == PROJECT_INDEX_URL else '<html>无</html>')
    patch(monkeypatch, upstream, [listing_row('9999999999', '白金海岸')])
    report = collect_names(store, ['tmsf'])
    row = project_rows(store)[PID]
    assert row['name'] == '春来晴翠园', '详情失败不丢名单'
    assert row['market_state'] == 'new_house' and row['project_sale_status'] == '在售'
    assert '详情获取失败' in row['property_type_error']
    assert 'address' not in row
    assert any(e.get('source_id') == PID for e in report['errors'])
    assert report['phase'] == 'partial_failed'


def test_rerun_is_idempotent_cached_and_ignored_survives(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    upstream, calls = client()
    patch(monkeypatch, upstream, [listing_row('9999999999', '白金海岸')])
    collect_names(store, ['tmsf'])
    calls.clear()
    report = collect_names(store, ['tmsf'])
    assert report['new'] == 0 and len(project_rows(store)) == 2, '重跑不重复'
    assert not [u for u in calls if '/newhouse/property_' in u], '30 天内详情走缓存'
    rid = next(r['id'] for r in store.sources() if r.get('source_kind') == 'project')
    store.ignore_source(rid)
    calls.clear()
    collect_names(store, ['tmsf'])
    ignored = next(r for r in store.sources() if r['id'] == rid)
    assert ignored['status'] == 'ignored', '忽略项不复活'
    assert not any(f'/newhouse/property_{ignored["source_id"]}_' in u for u in calls), '忽略项不再请求详情'


def test_esf_covered_project_not_rediscovered(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    only_selling = 'var data_auto = ' + json.dumps([SELLING], ensure_ascii=False)
    upstream, _ = client(projects=[SELLING], index=only_selling)
    patch(monkeypatch, upstream, [listing_row('3017629894', '春来晴翠园')])
    collect_names(store, ['tmsf'])
    assert project_rows(store) == {}, '名录已覆盖的项目不生成重复候选'
    community = next(r for r in store.sources() if r.get('source_kind') == 'community')
    assert community['market_state'] == 'new_house' and community['project_id'] == PID
    assert community['property_type'] == '住宅', '既有小区继续走新房补充匹配'


def test_same_numeric_id_kinds_stay_isolated(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    twin = dict(SELLING, propertyid=8888888888, propertyname='春来晴翠园')
    twin_index = 'var data_auto = ' + json.dumps([twin], ensure_ascii=False)
    esf = ('<input id="communityname_auto" value="白金海岸">'
           '<input id="managetypename_auto" value="住宅">')
    upstream, _ = client(projects=[twin], index=twin_index, community=esf)
    patch(monkeypatch, upstream, [listing_row('8888888888', '白金海岸')])
    collect_names(store, ['tmsf'])
    rows = {r['source_kind']: r for r in store.sources() if r['source_id'] == '8888888888'}
    assert rows['community']['name'] == '白金海岸' and rows['community']['property_type'] == '住宅'
    assert 'project_id' not in rows['community'], '小区证据不得混入新房字段'
    assert rows['project']['name'] == '春来晴翠园' and rows['project']['project_id'] == '8888888888'
    (tmp_path / 'property_types.json').write_text(json.dumps({'8888888888': dict(
        property_type='写字楼', url='u', captured_at='2026-01-01T00:00:00+00:00')}, ensure_ascii=False))
    leaked = historical_evidence(dict(source='tmsf', source_kind='project', source_id='8888888888',
                                      name='春来晴翠园', district='滨江'), tmp_path)
    assert leaked == {}, 'project 来源不得读取小区历史事实'


def test_truncated_address_stays_unverified(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    pages = {SELLING['propertyid']: page(address='滨江区江晖路2030号', truncate=True)}
    upstream, _ = client(projects=[SELLING])
    upstream.fetch_text = lambda url, timeout: (
        pages[int(url.split('_')[-2])] if '/newhouse/property_' in url
        else INDEX if url == PROJECT_INDEX_URL else '<html>无</html>')
    patch(monkeypatch, upstream, [listing_row('9999999999', '白金海岸')])
    collect_names(store, ['tmsf'])
    row = project_rows(store)[PID]
    assert 'address' not in row and 'address_checked_at' not in row, '截断地址不能成为成功事实'
    assert '截断' in (row.get('address_error') or ''), '地址失败独立可见'
    assert row.get('property_type_error') is None and row['property_type'] == '住宅', '用途证据不受地址影响'


def test_project_detail_by_id_and_inspected_selectors():
    upstream, calls = client(projects=[SELLING])
    facts = fetch_project_facts_by_id(upstream, siteid=33, propertyid=PID,
                                      names=['万科春来晴翠园', '春来晴翠园'], district='滨江')
    assert facts['property_type'] == '住宅' and facts['project_sale_status'] == '在售'
    assert facts['address'] == ADDRESS and facts['address_district'] == '滨江'
    assert facts['market_state'] == 'new_house'
    assert calls[-1].endswith(f'property_33_{PID}_infoUpgrade.htm')
    with pytest.raises(Exception):
        fetch_project_facts_by_id(upstream, siteid=33, propertyid=PID,
                                  names=['别的项目'], district='滨江')


def test_listing_gate_newhouse_exemption():
    new = dict(source='tmsf', source_kind='project', source_id='p1', name='春来晴翠园',
               market_state='new_house', project_id=PID, project_sale_status='在售')
    esf = dict(source='tmsf', source_kind='community', source_id='c1', name='春来晴翠园',
               market_state='second_hand', listing_count=1)
    assert listing_gate([esf])[0] == 'excluded', '纯二手房低挂牌仍排除'
    assert listing_gate([new, esf]) == (None, ''), '新房证据豁免混合小区低挂牌'
    assert listing_gate([new]) == (None, '')
    sold = {**new, 'market_state': 'second_hand', 'project_sale_status': '售完'}
    assert listing_gate([sold, esf])[0] == 'excluded', '售完项目不豁免'
    legacy_new = {**new, 'project_id': None}
    assert listing_gate([legacy_new])[0] is None, '旧格式新房标记按存储值豁免'


def test_mixed_market_view_projects_new_house(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    cid = store.create('春来晴翠园', district='滨江', address=ADDRESS, community_id='local-x')['community_id']
    esf = store.ingest(dict(source='tmsf', source_kind='community', source_id='3017629894', name='春来晴翠园',
                            district='滨江', market_state='second_hand', listing_count=3,
                            property_type='住宅', property_type_checked_at='2026-01-01T00:00:00+00:00',
                            address=ADDRESS, address_checked_at='2026-01-01T00:00:00+00:00'))
    project = store.ingest(dict(source='tmsf', source_kind='project', source_id=PID, name='春来晴翠园',
                                district='滨江', market_state='new_house', project_id=PID,
                                project_sale_status='在售', project_siteid='33', property_type='住宅',
                                property_type_checked_at='2026-01-01T00:00:00+00:00', address=ADDRESS,
                                address_origin='source_detail', address_checked_at='2026-01-01T00:00:00+00:00'))
    store.associate(esf['id'], cid)
    store.associate(project['id'], cid)
    view = community_views(store, tmp_path)[0]
    assert view['market_state'] == 'new_house', '混合市场按有效新房证据投影'
    assert view['market_state_conflict'], '并存来源保留冲突标记'


def test_eligible_project_materializes_incomplete_stays_pending(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    complete = store.ingest(dict(source='tmsf', source_kind='project', source_id=PID, name='春来晴翠园',
                                 aliases=['万科春来晴翠园'], district='滨江', market_state='new_house',
                                 project_id=PID, project_sale_status='在售', property_type='住宅',
                                 property_type_checked_at='2026-01-01T00:00:00+00:00', address=ADDRESS,
                                 address_origin='source_detail', address_checked_at='2026-01-01T00:00:00+00:00'))
    with store.db() as db:
        assert materialize(store, db, {}) == 1
    views = community_views(store, tmp_path)
    assert views[0]['admission_state'] == 'admitted' and views[0]['market_state'] == 'new_house'
    assert next(s for s in store.sources() if s['id'] == complete['id'])['status'] == 'matched'
    missing = store.ingest(dict(source='tmsf', source_kind='project', source_id=str(WAIT['propertyid']),
                                name='泊玺骏庐', district='滨江', market_state='new_house',
                                project_id=str(WAIT['propertyid']), project_sale_status='待售',
                                property_type='住宅', property_type_checked_at='2026-01-01T00:00:00+00:00'))
    with store.db() as db:
        materialize(store, db, {})
    assert next(s for s in store.sources() if s['id'] == missing['id'])['status'] == 'pending', '缺有效地址留待补'
    rows = inventory(store, tmp_path)
    row = next(r for r in rows if r.get('source_record_id') == missing['id'])
    assert row['admission_state'] == 'excluded' and row['qualification'] == 'address_missing'
    assert row['market_state'] == 'new_house', '待补候选可见且带市场投影'


def test_enrich_project_source_never_builds_esf_url(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    row = store.ingest(dict(source='tmsf', source_kind='project', source_id=PID, name='万科春来晴翠园',
                            aliases=['春来晴翠园'], district='滨江', market_state='new_house',
                            project_id=PID, project_sale_status='在售', project_siteid='33'))
    upstream, calls = client(projects=[SELLING])
    report = enrich_source(store, tmp_path, row['id'], tmsf_client=upstream, include_position=False)
    assert not [u for u in calls if '/esf/' in u], '新房来源补全不得请求二手房页'
    updated = next(s for s in store.sources() if s['id'] == row['id'])
    assert updated['property_type'] == '住宅' and updated['address'] == ADDRESS
    assert report['errors'] == []


def test_price_refresh_never_treats_project_id_as_esf(tmp_path):
    import asyncio
    from src.services.community_registry import existing_registry
    from src.services import refresh
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    store.ingest(dict(source='tmsf', source_kind='project', source_id='8888888888', name='春来晴翠园',
                      district='滨江', market_state='new_house', project_id='8888888888', project_siteid='33'))
    assert existing_registry(tmp_path)

    def fake_fetcher(community_id, *, timeout):
        raise AssertionError('project sid 不得进入价格采集')

    async def scenario():
        await refresh.run_refresh_once(['8888888888'], tmp_path / 's.jsonl', tmp_path / 'b.jsonl',
                                       tmp_path, fetcher=fake_fetcher, sleep_seconds=0)
    with pytest.raises(RuntimeError):
        asyncio.run(scenario()), '无 community 来源时本轮无价格可采'


def test_newhouse_index_failure_reported_without_losing_tmsf(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    upstream, _ = client(index=None, projects=[SELLING])
    patch(monkeypatch, upstream, [listing_row('9999999999', '白金海岸')])
    report = collect_names(store, ['tmsf'])
    assert report['phase'] == 'partial_failed' and store.sources(), '二手房采集不受新房索引失败影响'
    assert any(e.get('stage') == 'newhouse_index' for e in report['errors'])
    assert project_rows(store) == {}, '索引不可用时本轮无新房候选'


def test_legacy_fact_lookups_skip_project_kind():
    from src.api.directory_routes import source_view
    from src.services.directory_workflow import catalog_property_types
    from src.services.community_admission import effective_type
    record = dict(source='tmsf', source_kind='project', source_id='8888888888', name='春来晴翠园', status='pending')
    legacy = {'8888888888': dict(property_type='写字楼')}
    assert 'property_type' not in source_view(record, legacy), '来源视图不串小区历史用途'
    assert catalog_property_types({'sources': [record]}, legacy) == []
    assert effective_type([record], legacy) == '住宅', '有效类型投影不受污染'


def test_newhouse_review_member_keeps_type_without_legacy_leak():
    from src.services.residential_classifier import classify_sources
    record = dict(source='tmsf', source_kind='project', source_id='8888888888', name='春来晴翠园', status='pending')
    legacy = {'8888888888': dict(property_type='写字楼')}
    assert classify_sources([record], legacy) == 'pending', 'project 来源无用途时不得继承小区历史类型'
    typed = {**record, 'property_type': '住宅', 'property_type_checked_at': '2026-01-01T00:00:00+00:00'}
    assert classify_sources([typed], legacy) == 'residential'
