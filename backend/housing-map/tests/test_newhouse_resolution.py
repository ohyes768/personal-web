import json
import threading
from types import SimpleNamespace

import pytest

from src.services.community_registry import CommunityRegistry, dump
from src.services.directory_policy import eligibility, KEY as FLOW_KEY, VERSION as FLOW_RULE
from src.services.directory_position_state import identity, position_view
from src.services.directory_workflow import inventory, synchronize

KEY = 'admission_address_policy'
RULE = 'amap-subject-address-v1'


def candidate():
    c = dict(community_id='c', community_name='测试住宅', district='滨江', address='', aliases=[],
             collection_pipeline_version='collection-pipeline-v2', admission_address_policy=RULE)
    point = dict(source_id='P1', name=c['community_name'], district='滨江', address='月明路1076号',
                 longitude=120.20749, latitude=30.20226, coordinate_system='gcj02',
                 poi_typecode='120302', poi_type='住宅小区')
    c['amap_position'] = dict(identity=identity(c), state='matched', selected=point, candidates=[point])
    return c


def source(**extra):
    return dict(source='tmsf', source_kind='project', source_id='101', name='测试住宅', district='滨江',
                property_type='住宅', market_state='new_house', address='', **extra)


def test_reliable_amap_address_meets_address_gate_only_when_enabled():
    c = candidate()
    assert eligibility(c, [source()])['admission_state'] == 'admitted'
    c.pop(KEY)
    assert eligibility(c, [source()])['qualification'] == 'address_missing'


@pytest.mark.parametrize('change', [dict(address=''), dict(district='萧山'), dict(poi_typecode='050000'),
                                 dict(name='测试住宅二期'), dict(address='滨江区..'), dict(latitude=0)])
def test_unreliable_subject_cannot_supply_admission_address(change):
    c = candidate(); c['amap_position']['selected'].update(change)
    assert eligibility(c, [source()])['admission_state'] != 'admitted'


def test_literal_nonresidential_finishes_without_address():
    r = source(); r['property_type'] = '非住宅'
    assert eligibility(candidate(), [r])['qualification'] == 'use_conflict'
    c = candidate(); c.pop('amap_position')
    assert eligibility(c, [r])['qualification'] == 'non_residential'


def test_amap_projection_preserves_identity_and_raw_sources(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    with store.db() as db:
        for k, v in [(FLOW_KEY, FLOW_RULE), ('collection_pipeline_version', 'collection-pipeline-v2'), (KEY, RULE)]:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (k, v))
    store.ingest(source()); synchronize(store, tmp_path)
    row = inventory(store, tmp_path)[0]
    with store.db() as db:
        raw = db.execute('SELECT payload FROM communities WHERE id=?', (row['community_id'],)).fetchone()[0]
        c = json.loads(raw)
        c.update({k: v for k, v in candidate().items() if k not in {'community_id', 'amap_position'}})
        c['amap_position'] = candidate()['amap_position']
        c['amap_position']['identity'] = identity(c)
        c.update(longitude=120.20749, latitude=30.20226, coordinate_system='gcj02')
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(c), row['community_id']))
    view = inventory(store, tmp_path)[0]
    assert view['address'] == '月明路1076号'
    assert view['address_evidence']['origin'] == 'amap_subject'
    assert view['admission_state'] == 'admitted' and view['map_status'] == 'displayed'
    assert position_view(view, view['sources'])['state'] == 'matched'
    assert view['sources'][0]['address'] == ''
    with store.db() as db:
        assert json.loads(db.execute('SELECT payload FROM communities').fetchone()[0])['address'] == ''


def test_basic_project_mode_never_requests_certificate():
    from src.services.tmsf_property_type import fetch_project_facts_by_id
    calls = []
    html = ('<div class="house_float_name_title">测试住宅</div><a id="districtname">滨江楼盘</a>'
            '<div class="house_float_name_tips_grey">住宅</div><div class="house_float_name_tips_greenlight">在售</div>'
            '<div>楼盘地址</div><div>月明路..</div><a href="/newhouse/presell_33_101_202.htm">202600001</a>')
    def fetch(url, timeout): calls.append(url); return html
    client = SimpleNamespace(fetch_text=fetch, fetch_project_text=fetch)
    value = fetch_project_facts_by_id(client, siteid='33', propertyid='101', names=['测试住宅'],
                                     district='滨江', supplement_address=False)
    assert value['property_type'] == '住宅' and value['address_pending']
    assert len(calls) == 1


def test_address_only_and_identity_conflicts_are_not_browser_retry_targets():
    from src.services.directory_collection import retryable_sources
    rows = [source(address_error='预售证项目或证号不一致', property_type_checked_at='2026-10-27'),
            source(property_type_error='详情失败', collection_error_code='identity_mismatch'),
            source(property_type_error='超时', collection_error_code='browser_timeout')]
    assert retryable_sources(rows) == [rows[2]]


def test_address_policy_preview_apply_disable_preserves_later_writes(tmp_path):
    from src.services.address_policy_migration import preview, apply, disable
    data = tmp_path / 'data'; data.mkdir()
    store = CommunityRegistry(data / 'community_registry.sqlite3')
    with store.db() as db:
        for k, v in [(FLOW_KEY, FLOW_RULE), ('collection_pipeline_version', 'collection-pipeline-v2')]:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (k, v))
    store.ingest(source()); synchronize(store, data)
    cid = inventory(store, data)[0]['community_id']
    with store.db() as db:
        c = json.loads(db.execute('SELECT payload FROM communities').fetchone()[0])
        c['amap_position'] = candidate()['amap_position']
        c['amap_position']['identity'] = identity(c)
        db.execute('UPDATE communities SET payload=?', (dump(c),))
    before = store.path.read_bytes()
    plan = preview(data)
    assert store.path.read_bytes() == before
    assert plan['changes'][0]['after'] == 'admitted'
    with pytest.raises(ValueError, match='维护'): apply(data, plan, tmp_path / 'backup')
    apply(data, plan, tmp_path / 'backup', maintenance=True)
    assert inventory(store, data)[0]['admission_state'] == 'admitted'
    with store.db() as db:
        c = json.loads(db.execute('SELECT payload FROM communities').fetchone()[0]); c['note'] = 'later write'
        db.execute('UPDATE communities SET payload=?', (dump(c),))
    disable(data, maintenance=True)
    assert inventory(store, data)[0]['qualification'] == 'address_missing'
    with store.db() as db:
        assert json.loads(db.execute('SELECT payload FROM communities').fetchone()[0])['note'] == 'later write'


def test_collection_followup_reuses_shared_position_job_and_only_current_sources(tmp_path, monkeypatch):
    from src.services.directory_collection import DirectoryJob
    from src.services import directory_position
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    with store.db() as db:
        for k, v in [(FLOW_KEY, FLOW_RULE), ('collection_pipeline_version', 'collection-pipeline-v2'), (KEY, RULE)]:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (k, v))
    store.ingest(source(address_pending=True)); synchronize(store, tmp_path)
    calls = []
    shared = SimpleNamespace(start=lambda **kw: calls.append(kw), worker=None)
    monkeypatch.setattr(directory_position, 'get_position_job', lambda _: shared, raising=False)
    job = DirectoryJob(store)
    assert job._match_sources({('tmsf', 'project', '101')})['state'] == 'started'
    assert calls == [dict(community_ids=[inventory(store, tmp_path)[0]['community_id']])]
    shared.start = lambda **kw: (_ for _ in ()).throw(ValueError('高德信息正在采集'))
    assert job._match_sources({('tmsf', 'project', '101')})['state'] == 'pending'
    job.cancel.set()
    assert job._match_sources({('tmsf', 'project', '101')})['state'] == 'cancelled'


def test_18_project_batch_separates_facts_identity_and_transport_without_certificates(tmp_path, monkeypatch):
    from scripts import fetch_tmsf_binjiang_communities as listing
    from src.services import directory_collection as collection
    from src.services.tmsf_fetcher import TmsfClient
    from src.services.tmsf_browser import BrowserClient, BrowserFetchError
    projects = [dict(siteid=33, propertyid=100+i, propertyname=f'测试楼盘{i}',
                     districtname='滨江', propertystateid=2) for i in range(18)]
    monkeypatch.setattr(listing, 'fetch_binjiang_communities', lambda: [])
    monkeypatch.setattr(collection, 'pause', lambda _: None)
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', 'http://worker')
    monkeypatch.setattr(TmsfClient, 'fetch_text', lambda *_: 'var data_auto = '+json.dumps(projects))
    requests = []
    def request(self, path, body, timeout):
        if path == '/close': return {}
        requests.append(body)
        assert 'presellid' not in body
        i = int(body['propertyid']) - 100
        if i in {14, 15}: raise BrowserFetchError('browser_timeout', '页面超时')
        if i == 16: raise BrowserFetchError('manual_verification', '需要验证')
        name = f'测试楼盘{i}' if i not in {12, 13} else '另一个楼盘'
        prop = '非住宅' if i < 4 else '住宅'
        address = '月明路100号' if 9 <= i < 12 else '月明路..'
        html = (f'<div class="house_float_name_title">{name}</div><a id="districtname">滨江楼盘</a>'
                f'<div class="house_float_name_tips_grey">{prop}</div>'
                '<div class="house_float_name_tips_greenlight">在售</div>'
                f'<div>楼盘地址</div><div>{address}</div><a href="/newhouse/presell_33_{100+i}_202.htm">202600001</a>')
        return dict(url=f'https://www.tmsf.com/newhouse/property_33_{100+i}_infoUpgrade.htm', html=html)
    monkeypatch.setattr(BrowserClient, '_request', request)
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    report = collection.collect_names(store, ['tmsf'])
    assert len(store.sources()) == 18 and len(requests) == 17
    assert (report['property_types'], report['property_types_review'], report['property_types_failed'], report['property_types_deferred']) == (12, 2, 3, 1)
    assert len(report['evidence_issues']) == 2 and len(report['errors']) == 3
    assert report['newhouse_pause_reason'] == 'manual_verification'


def test_project_stage_failure_remains_pending_until_repaired():
    c = candidate()
    r = source(collection_error_code='identity_mismatch', property_type_error='项目身份核对失败')
    assert eligibility(c, [r])['qualification'] == 'identity_conflict'
    r['collection_error_code'] = None; r['property_type_error'] = None
    assert eligibility(c, [r])['admission_state'] == 'admitted'


def test_followup_error_keeps_saved_facts_and_finishes_job(tmp_path):
    from src.services.directory_collection import collect_names
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    def adapter(*_): yield source()
    def fail(_): raise RuntimeError('followup unavailable')
    report = collect_names(store, ['tmsf'], adapters={'tmsf': adapter}, after_collect=fail)
    assert report['running'] is False and report['phase'] == 'partial_failed'
    assert len(store.sources()) == 1
    assert report['position_followup']['state'] == 'failed'
