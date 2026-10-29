"""租金查询与刷新路由契约测试（离线：tmp 数据目录 + fake service）。

契约来源：apps/housing-map/src/lib/rental-types.ts 与任务 design.md
"Query API" / "Web refresh"；响应形状以探针验证的真实行为为准。
"""
import asyncio
import datetime as dt
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.rental_routes as rental_routes
from src.api.rental_routes import _external_job, _external_phase, _last_refresh_of
from src.services.rental_reference.refresh import (
    RefreshAlreadyRunning,
    RefreshNotRunning,
)

CID_MAPPED = '10001039'
CID_MAPPED_2 = '10004141'
CID_UNVERIFIED = '20044031'
CID_UNMAPPED = '90000001'
CID_UNKNOWN = '88888888'
SRC_ID = '2010067741'

COMMUNITIES = [
    {'community_id': CID_MAPPED, 'community_name': '风雅钱塘世纪花园'},
    {'community_id': CID_MAPPED_2, 'community_name': '欣盛东方郡'},
    {'community_id': CID_UNVERIFIED, 'community_name': '万科璞悦湾'},
    {'community_id': CID_UNMAPPED, 'community_name': '无映射小区'},
]

SUMMARY_DATA_KEYS = {'area_band', 'bedrooms', 'summaries'}
SUMMARY_ENTRY_KEYS = {'community_id', 'availability', 'last_refresh', 'sample_count',
                      'captured_at', 'unit_rent_yuan_m2_month',
                      'annualized_gross_yield_pct'}
DETAIL_DATA_KEYS = {'availability', 'last_refresh', 'sample_count', 'excluded_count',
                    'captured_at', 'regional_sample', 'sampling', 'groups', 'bedrooms_distribution',
                    'samples', 'page', 'page_size', 'total', 'source_links'}
GROUP_KEYS = {'bedrooms', 'area_band', 'sample_count', 'rent_reference',
              'sale_reference', 'yield_estimate'}
JOB_KEYS = {'stage', 'association', 'job_id', 'running', 'phase', 'total_communities',
            'processed_communities', 'current_community_id', 'pages_fetched',
            'details_fetched', 'success_count', 'failed_count', 'started_at',
            'finished_at', 'last_success_at', 'errors', 'result', 'request_count',
            'detail_cache_hits', 'reused_communities', 'deferred_count', 'cooldown_until', 'new_sources_deferred'}


def test_request_diagnostics_old_jobs_and_new_pause_state():
    old = _external_job({'phase': 'done'})
    assert old['request_count'] == 0 and old['cooldown_until'] is None
    new = _external_job({'phase': 'done', 'deferred_count': 3, 'cooldown_until': '2026-10-18T10:00:00+00:00'})
    assert new['deferred_count'] == 3 and new['phase'] == 'partial_failed'


def now_iso(days=0):
    return (dt.datetime.now(dt.UTC) + dt.timedelta(days=days)).isoformat()


def smp(lid, rent=9000.0, area=100.0, layout='3室2厅', mode='whole', prop='住宅',
        detail=True, floor='5', captured=None, url=None):
    """与采集输出同形的样本；A/B/C 三个默认样本 = unit rent 90/75/100。"""
    return {
        'source': 'fang',
        'source_listing_id': lid,
        'source_url': url if url is not None
        else f'https://zu.fang.com/hz/chuzu/3_{lid}_1.htm',
        'source_community_id': SRC_ID,
        'community_name': '风雅钱塘世纪花园',
        'title': f'出租{lid}',
        'monthly_rent_yuan': rent,
        'area_m2': area,
        'layout': layout,
        'rental_mode': mode,
        'property_type': prop,
        'quality_flags': [],
        'detail_fetched': detail,
        'floor': floor,
        'captured_at': captured or now_iso(),
    }


def valid3():
    return [smp('A', 9000.0, 100.0), smp('B', 7500.0, 100.0), smp('C', 12000.0, 120.0)]


def entry(cid, samples, captured=None, src=SRC_ID, quality=None):
    return {'community_id': cid, 'source': 'fang', 'source_community_id': src,
            'captured_at': captured or now_iso(), 'samples': samples,
            'quality': quality or {}, 'status': 'complete'}


def publish(rentals_dir, communities, run_id='run-1'):
    """按 storage.load_current 可读布局写一个已发布版本。"""
    published_at = now_iso()
    run_dir = rentals_dir / 'runs' / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'batch.json').write_text(json.dumps({
        'version': 1, 'run_id': run_id, 'published_at': published_at,
        'communities': communities}), encoding='utf-8')
    (rentals_dir / 'current.json').write_text(json.dumps({
        'version': 1, 'run_id': run_id, 'published_at': published_at}),
        encoding='utf-8')


def write_maps(path, entries):
    path.write_text(json.dumps({'version': 1, 'mappings': entries}), encoding='utf-8')


def mp(src, cid, status='verified'):
    return {'source': 'fang', 'source_community_id': src, 'community_id': cid,
            'source_name': 'x', 'source_address': None, 'status': status}


def job(**over):
    base = {
        'job_id': 'job-1', 'running': False, 'phase': 'done',
        'total_communities': 3, 'processed_communities': 3,
        'current_community_id': None, 'pages_fetched': 5, 'details_fetched': 7,
        'success_count': 2, 'failed_count': 1,
        'started_at': now_iso(-1), 'finished_at': now_iso(),
        'last_success_at': now_iso(),
        'errors': {'total': 1, 'items': [
            {'community_id': CID_MAPPED, 'stage': 'detail', 'error': 'detail failed'}]},
        'result': {'published': True, 'run_id': 'r1', 'reason': None,
                   'published_at': now_iso(), 'adopted': ['a', 'b'],
                   'carried_over': ['c'], 'absent': []},
    }
    base.update(over)
    return base


class FakeSvc:
    """RentalRefreshService 的 duck-typing 替身。"""

    def __init__(self, snapshot=None, start_error=None, cancel_error=None):
        self.snapshot = snapshot if snapshot is not None else {
            'job_id': None, 'running': False, 'phase': 'idle',
            'total_communities': 0, 'processed_communities': 0,
            'current_community_id': None, 'pages_fetched': 0, 'details_fetched': 0,
            'success_count': 0, 'failed_count': 0,
            'started_at': None, 'finished_at': None, 'last_success_at': None,
            'errors': {'total': 0, 'items': []}, 'result': None,
        }
        self.start_error = start_error
        self.cancel_error = cancel_error
        self.start_calls = 0
        self.shutdown_called = False

    def start(self):
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        self.snapshot = {**self.snapshot, 'job_id': 'fresh-job', 'running': True,
                         'phase': 'crawling', 'started_at': now_iso()}
        return self.snapshot

    def cancel(self):
        if self.cancel_error is not None:
            raise self.cancel_error
        self.snapshot = {**self.snapshot, 'phase': 'cancelling'}
        return self.snapshot

    def status(self):
        return self.snapshot

    def shutdown(self, timeout=30.0):
        self.shutdown_called = True
        return True


_app = FastAPI()
_app.include_router(rental_routes.router)
client = TestClient(_app)


@pytest.fixture()
def api_env(tmp_path, monkeypatch):
    """隔离环境：tmp rentals 目录 + verified/unverified 台账 + 空售价 + 无任务。"""
    rentals_dir = tmp_path / 'rentals'
    rentals_dir.mkdir()
    mappings_path = tmp_path / 'rental_community_mappings.json'
    write_maps(mappings_path, [
        mp(SRC_ID, CID_MAPPED),
        mp('2010356262', CID_MAPPED_2),
        mp('2011095896', CID_UNVERIFIED, status='unverified'),
    ])
    monkeypatch.setattr(rental_routes, '_rentals_dir', rentals_dir)
    monkeypatch.setattr(rental_routes, '_mappings_path', mappings_path)
    monkeypatch.setattr(rental_routes, '_service', None)
    monkeypatch.setattr(rental_routes, 'load_communities', lambda: COMMUNITIES)
    monkeypatch.setattr(rental_routes, 'load_price_snapshots', lambda: {})
    return rentals_dir


def summaries(params=None):
    """GET summary 并按 community_id 建索引。"""
    resp = client.get('/rentals/summary', params=params)
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    assert set(body['data'].keys()) == SUMMARY_DATA_KEYS
    return {e['community_id']: e for e in body['data']['summaries']}


def detail(cid, params=None):
    resp = client.get(f'/communities/{cid}/rentals', params=params)
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    assert set(body['data'].keys()) == DETAIL_DATA_KEYS
    return body['data']


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def test_summary_available_with_listing_yield(api_env, monkeypatch):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    monkeypatch.setattr(rental_routes, 'load_price_snapshots', lambda: {
        CID_MAPPED: {'price': 30000, 'price_type': 'listing_avg',
                     'date': '2026-10-10', 'listing_count': 5}})
    rows = summaries({'area_band': '90to144', 'bedrooms': 'all'})
    assert set(rows.keys()) == {c['community_id'] for c in COMMUNITIES}
    row = rows[CID_MAPPED]
    assert set(row.keys()) == SUMMARY_ENTRY_KEYS
    assert row['availability'] == 'available'
    assert row['sample_count'] == 3
    assert row['unit_rent_yuan_m2_month'] == pytest.approx(90.0)
    assert row['annualized_gross_yield_pct'] == pytest.approx(90 * 12 / 30000 * 100)
    assert row['captured_at'] is not None
    assert row['last_refresh'] is None  # 从未跑过刷新


def test_summary_signed_basis_yield(api_env, monkeypatch):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    monkeypatch.setattr(rental_routes, 'load_price_snapshots', lambda: {
        CID_MAPPED: {'price': 36000, 'price_type': 'monthly_deal_avg_latest',
                     'date': '2026-10-01', 'deal_count': 3}})
    row = summaries({'area_band': '90to144'})[CID_MAPPED]
    assert row['annualized_gross_yield_pct'] == pytest.approx(90 * 12 / 36000 * 100)


def test_summary_unmapped_and_unverified(api_env):
    rows = summaries()
    assert rows[CID_UNMAPPED]['availability'] == 'unmapped'
    # 未核验台账条目不能当映射用（未核验不发布关联）
    assert rows[CID_UNVERIFIED]['availability'] == 'unmapped'
    assert rows[CID_UNMAPPED]['sample_count'] == 0
    assert rows[CID_UNMAPPED]['unit_rent_yuan_m2_month'] is None


def test_summary_no_samples_when_published_empty(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, [])})
    row = summaries()[CID_MAPPED]
    assert row['availability'] == 'no_samples'
    assert row['sample_count'] == 0
    assert row['unit_rent_yuan_m2_month'] is None


def test_summary_insufficient_samples(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3()[:2])})
    row = summaries()[CID_MAPPED]
    assert row['availability'] == 'insufficient_samples'
    assert row['sample_count'] == 2
    assert row['unit_rent_yuan_m2_month'] is None
    assert row['annualized_gross_yield_pct'] is None


def test_summary_stale_keeps_unit_rent_stops_yield(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3(),
                                        captured=now_iso(-40))})
    row = summaries()[CID_MAPPED]
    assert row['availability'] == 'stale'
    assert row['unit_rent_yuan_m2_month'] == pytest.approx(90.0)
    assert row['annualized_gross_yield_pct'] is None


def test_summary_missing_price_nulls_yield_only(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    row = summaries()[CID_MAPPED]
    assert row['availability'] == 'available'
    assert row['unit_rent_yuan_m2_month'] == pytest.approx(90.0)
    assert row['annualized_gross_yield_pct'] is None  # 缺售价只停收益


def test_summary_source_failed_without_published_data(api_env, monkeypatch):
    monkeypatch.setattr(rental_routes, '_service', FakeSvc(
        snapshot=job(phase='failed', running=False,
                     result={'published': False, 'reason': 'all_failed'})))
    row = summaries()[CID_MAPPED]
    assert row['availability'] == 'source_failed'
    assert row['last_refresh']['status'] == 'failed'
    assert row['last_refresh']['error'] == 'detail failed'
    assert row['captured_at'] is None


def test_summary_available_with_failed_refresh_coexist(api_env, monkeypatch):
    """旧数据可用 + 最近抓取失败并存（契约 3）。"""
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    monkeypatch.setattr(rental_routes, '_service', FakeSvc(
        snapshot=job(phase='failed', running=False,
                     result={'published': False, 'reason': 'all_failed'})))
    row = summaries()[CID_MAPPED]
    assert row['availability'] == 'available'
    assert row['last_refresh']['status'] == 'failed'


def test_summary_all_band_4plus_scope(api_env):
    samples = [smp('D', 4000.0, 80.0, layout='4室2厅'),
               smp('E', 6000.0, 100.0, layout='5室1厅'),
               smp('F', 8000.0, 120.0, layout='4室2厅')]
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, samples)})
    row = summaries({'area_band': 'all', 'bedrooms': '4plus'})[CID_MAPPED]
    assert row['availability'] == 'available'
    assert row['sample_count'] == 3  # >=4 室跨面积段合并，5室也算 4plus
    assert row['unit_rent_yuan_m2_month'] == pytest.approx(60.0)  # 50/60/66.7 中位


def test_summary_corrupt_mapping_file_503(api_env, monkeypatch):
    broken = api_env.parent / 'broken-summary.json'
    monkeypatch.setattr(rental_routes, '_mappings_path', broken)
    broken.write_text('{not json', encoding='utf-8')
    assert client.get('/rentals/summary').status_code == 503


def test_summary_last_refresh_running(api_env, monkeypatch):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    monkeypatch.setattr(rental_routes, '_service', FakeSvc(
        snapshot=job(phase='crawling', running=True, result=None,
                     finished_at=None)))
    row = summaries()[CID_MAPPED]
    assert row['last_refresh']['status'] == 'running'


# ---------------------------------------------------------------------------
# detail
# ---------------------------------------------------------------------------

def test_detail_unknown_community_404(api_env):
    assert client.get(f'/communities/{CID_UNKNOWN}/rentals').status_code == 404


def test_detail_known_but_unmapped_200(api_env):
    data = detail(CID_UNMAPPED)
    assert data['availability'] == 'unmapped'
    assert data['groups'] == []
    assert data['source_links'] == []


def test_detail_groups_structure_and_numbers(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    data = detail(CID_MAPPED, {'area_band': '90to144', 'bedrooms': 'all'})
    assert data['availability'] == 'available'
    assert data['sample_count'] == 3
    assert data['excluded_count'] == 0
    # 3 居组 + "全部房型合并重算"组
    assert [(g['bedrooms'], g['area_band']) for g in data['groups']] == \
        [(3, '90to144'), (None, '90to144')]
    for group in data['groups']:
        assert set(group.keys()) == GROUP_KEYS
    rent = data['groups'][0]['rent_reference']
    assert rent['median_month_rent_yuan'] == pytest.approx(9000.0)
    assert rent['median_unit_rent_yuan_m2_month'] == pytest.approx(90.0)
    assert rent['p25_unit_rent_yuan_m2_month'] == pytest.approx(82.5)
    assert rent['p75_unit_rent_yuan_m2_month'] == pytest.approx(95.0)
    assert rent['sample_count'] == 3
    assert data['groups'][0]['sale_reference'] is None
    assert data['groups'][0]['yield_estimate'] is None
    assert data['source_links'] == [f'https://zu.fang.com/hz/house-xm{SRC_ID}/']


def test_detail_sampling_marker_passed_through(api_env):
    """配额采样标记透传到详情响应；旧快照（无标记）为 null。"""
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3(), quality={
        'sampling': {'quota': 10, 'qualified': 10, 'sampled': 11}})})
    data = detail(CID_MAPPED)
    assert data['sampling'] == {'quota': 10, 'qualified': 10, 'sampled': 11}


def test_detail_without_sampling_marker_is_null(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    assert detail(CID_MAPPED)['sampling'] is None


def test_detail_group_under_three_samples(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3()[:2])})
    data = detail(CID_MAPPED)
    assert data['availability'] == 'insufficient_samples'
    assert all(g['rent_reference'] is None for g in data['groups'])
    assert all(g['yield_estimate'] is None for g in data['groups'])
    assert data['total'] == 2
    assert len(data['samples']) == 2


def test_detail_sale_reference_and_yield(api_env, monkeypatch):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    monkeypatch.setattr(rental_routes, 'load_price_snapshots', lambda: {
        CID_MAPPED: {'price': 30000, 'price_type': 'listing_avg',
                     'date': '2026-10-10'}})
    data = detail(CID_MAPPED, {'area_band': '90to144'})
    for group in data['groups']:
        assert group['sale_reference'] == {
            'unit_price_yuan_m2': 30000, 'price_kind': 'listing',
            'price_date': '2026-10-10'}
        assert group['yield_estimate']['annualized_gross_yield_pct'] == \
            pytest.approx(3.6)
        assert group['yield_estimate']['rent_to_sale_ratio'] == \
            pytest.approx(30000 / 90)


def test_detail_matches_summary_numbers(api_env, monkeypatch):
    """同一口径下详情组与看板摘要必须是同一数字（验收：详情/看板一致）。"""
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    monkeypatch.setattr(rental_routes, 'load_price_snapshots', lambda: {
        CID_MAPPED: {'price': 30000, 'price_type': 'listing_avg',
                     'date': '2026-10-10'}})
    row = summaries({'area_band': '90to144'})[CID_MAPPED]
    data = detail(CID_MAPPED, {'area_band': '90to144'})
    merged = next(g for g in data['groups'] if g['bedrooms'] is None)
    assert merged['rent_reference']['median_unit_rent_yuan_m2_month'] == \
        pytest.approx(row['unit_rent_yuan_m2_month'])
    assert merged['yield_estimate']['annualized_gross_yield_pct'] == \
        pytest.approx(row['annualized_gross_yield_pct'])
    assert merged['sample_count'] == row['sample_count']


def test_detail_pagination_server_side(api_env):
    # 属性各不相同（相同 居/面积/租金/楼层 会被"疑似重复"正确排除）
    samples = [smp(f'L{i:02d}', rent=5000.0 + i * 111.0) for i in range(11)]
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, samples)})
    page1 = detail(CID_MAPPED, {'page': 1, 'page_size': 10})
    page2 = detail(CID_MAPPED, {'page': 2, 'page_size': 10})
    assert page2['total'] == 11
    assert page2['page'] == 2
    assert page2['page_size'] == 10
    assert len(page2['samples']) == 1
    ids_page1 = {s['source_listing_id'] for s in page1['samples']}
    assert len(ids_page1) == 10
    assert page2['samples'][0]['source_listing_id'] not in ids_page1


def test_detail_excluded_view_reasons(api_env):
    samples = valid3() + [
        smp('S1', mode='shared'),   # rental_mode=shared → quality_flags 自动无关
        smp('S2', detail=False),    # 详情未核验
    ]
    samples[-2]['quality_flags'] = ['shared_rental']
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, samples)})
    data = detail(CID_MAPPED, {'view': 'excluded'})
    assert data['excluded_count'] == 2
    assert data['total'] == 2
    reasons = {s['source_listing_id']: s['exclude_reason'] for s in data['samples']}
    assert reasons['S1'] == 'shared_rental'
    assert reasons['S2'] == 'detail_not_verified'
    assert all('exclude_reason' in s for s in data['samples'])


def test_detail_suspect_duplicate_tracked_not_counted(api_env):
    dup = smp('A-dup', 9000.0, 100.0, layout='3室2厅', floor='5')
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3() + [dup])})
    valid_view = detail(CID_MAPPED)
    assert valid_view['sample_count'] == 3  # 疑似重复不计入样本数
    excluded_view = detail(CID_MAPPED, {'view': 'excluded'})
    assert excluded_view['excluded_count'] == 1
    assert excluded_view['samples'][0]['exclude_reason'] == 'suspected_duplicate'


def test_detail_nan_rent_never_serialized(api_env):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, [smp('NAN1', rent=float('nan'))])})
    data = detail(CID_MAPPED, {'view': 'excluded'})
    assert data['samples'][0]['exclude_reason'] == 'non_positive_value'
    assert data['samples'][0]['month_rent_yuan'] is None
    raw = json.dumps(data)
    assert 'NaN' not in raw and 'Infinity' not in raw


def test_detail_infinite_price_nulls_yield(api_env, monkeypatch):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3())})
    monkeypatch.setattr(rental_routes, 'load_price_snapshots', lambda: {
        CID_MAPPED: {'price': float('inf'), 'price_type': 'listing_avg',
                     'date': '2026-10-10'}})
    data = detail(CID_MAPPED)
    assert data['availability'] == 'available'
    assert all(g['sale_reference'] is None and g['yield_estimate'] is None
               for g in data['groups'])
    assert 'Infinity' not in json.dumps(data)


def test_detail_source_url_domain_whitelist(api_env):
    samples = valid3() + [
        smp('BAD1', rent=8800.0, url='http://zu.fang.com/hz/chuzu/3_BAD1_1.htm'),
        smp('BAD2', rent=8900.0, url='https://evil.example.com/hz/chuzu/3_BAD2_1.htm'),
    ]
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, samples)})
    data = detail(CID_MAPPED, {'area_band': '90to144'})
    rows = {s['source_listing_id']: s for s in data['samples']}
    assert rows['A']['source_url'].startswith('https://zu.fang.com/')
    assert rows['BAD1']['source_url'] is None  # 非 https
    assert rows['BAD2']['source_url'] is None  # 外域
    assert all(link.startswith('https://zu.fang.com/') for link in data['source_links'])


def test_xingfuli_links_are_exact_host_and_hangzhou_only():
    safe = 'https://m.xflapp.com/zufang/hz-7660466810168328198.html'
    assert rental_routes._safe_source_url(safe) == safe
    for bad in ['https://m.xflapp.com.evil/zufang/hz-1.html',
                'https://user@m.xflapp.com/zufang/hz-1.html',
                'https://m.xflapp.com/zufang/bj-1.html']:
        assert rental_routes._safe_source_url(bad) is None


def test_detail_stale_returns_details_without_yield(api_env, monkeypatch):
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, valid3(),
                                        captured=now_iso(-40))})
    monkeypatch.setattr(rental_routes, 'load_price_snapshots', lambda: {
        CID_MAPPED: {'price': 30000, 'price_type': 'listing_avg',
                     'date': '2026-10-10'}})
    data = detail(CID_MAPPED, {'area_band': '90to144'})
    assert data['availability'] == 'stale'
    assert data['total'] == 3  # 明细仍可看
    assert all(g['yield_estimate'] is None for g in data['groups'])
    assert all(g['rent_reference'] is not None for g in data['groups'])


def test_detail_area_band_filter_scopes(api_env):
    samples = valid3() + [smp('D', 4000.0, 80.0)]
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, samples)})
    data = detail(CID_MAPPED, {'area_band': 'lt90'})
    assert data['sample_count'] == 1
    assert data['total'] == 1
    assert data['samples'][0]['source_listing_id'] == 'D'
    # lt90 段：3 居组 + 全部房型合并重算组
    assert [(g['bedrooms'], g['area_band']) for g in data['groups']] == \
        [(3, 'lt90'), (None, 'lt90')]


def test_detail_4plus_group_labels_filter(api_env):
    samples = [smp('D', 4000.0, 80.0, layout='4室2厅'),
               smp('E', 6000.0, 100.0, layout='5室1厅'),
               smp('F', 8000.0, 120.0, layout='4室2厅')]
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, samples)})
    data = detail(CID_MAPPED, {'bedrooms': '4plus'})
    assert data['sample_count'] == 3
    # 契约 bedrooms 为 number|null；4plus 合并口径以 4 标注并附 bedrooms_filter
    assert all(g['bedrooms'] == 4 for g in data['groups'])
    assert all(g['bedrooms_filter'] == '4plus' for g in data['groups'])
    lt90 = next(g for g in data['groups'] if g['area_band'] == 'lt90')
    assert lt90['sample_count'] == 1
    assert lt90['rent_reference'] is None


def test_detail_bedrooms_distribution_valid_only(api_env):
    samples = valid3() + [smp('S1', mode='shared')]
    samples[-1]['quality_flags'] = ['shared_rental']
    publish(api_env, {CID_MAPPED: entry(CID_MAPPED, samples)})
    data = detail(CID_MAPPED)
    assert data['bedrooms_distribution'] == {'3': 3}  # 排除样本不进分布


def test_detail_corrupt_mapping_file_503(api_env, monkeypatch):
    broken = api_env.parent / 'broken-detail.json'
    monkeypatch.setattr(rental_routes, '_mappings_path', broken)
    broken.write_text('[]', encoding='utf-8')  # 结构非法
    assert client.get(f'/communities/{CID_MAPPED}/rentals').status_code == 503


def test_detail_invalid_query_422(api_env):
    assert client.get(f'/communities/{CID_MAPPED}/rentals',
                      params={'area_band': 'huge'}).status_code == 422
    assert client.get(f'/communities/{CID_MAPPED}/rentals',
                      params={'page': 0}).status_code == 422


# ---------------------------------------------------------------------------
# 刷新任务路由
# ---------------------------------------------------------------------------

def test_refresh_get_without_job_null_data(api_env):
    resp = client.get('/rentals/refresh')
    assert resp.status_code == 200
    assert resp.json() == {'success': True, 'data': None}


def test_refresh_get_with_job_external_shape(api_env, monkeypatch):
    monkeypatch.setattr(rental_routes, '_service', FakeSvc(job()))
    resp = client.get('/rentals/refresh')
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    assert set(body['data'].keys()) == JOB_KEYS
    assert body['data']['phase'] == 'partial_failed'  # carried_over 非空
    assert body['data']['errors'] == {
        'items': [{'community_id': CID_MAPPED, 'message': 'detail failed'}],
        'total': 1}
    assert body['data']['result'] == {'published': True, 'success_count': 2,
                                      'failed_count': 1}


def test_refresh_post_starts_202(api_env, monkeypatch):
    svc = FakeSvc()
    monkeypatch.setattr(rental_routes, '_service', svc)
    resp = client.post('/rentals/refresh')
    assert resp.status_code == 202
    assert resp.json()['success'] is True
    assert resp.json()['data']['phase'] == 'running'
    assert svc.start_calls == 1


def test_refresh_post_conflict_409(api_env, monkeypatch):
    monkeypatch.setattr(rental_routes, '_service', FakeSvc(
        start_error=RefreshAlreadyRunning('busy')))
    resp = client.post('/rentals/refresh')
    assert resp.status_code == 409
    assert resp.json()['success'] is False


def test_refresh_post_no_verified_mappings_422(api_env):
    """不替换 service：走真实 service 的台账校验路径（tmp 台账只有 unverified）。"""
    write_maps(api_env.parent / 'rental_community_mappings.json', [
        mp(SRC_ID, CID_MAPPED, status='unverified')])
    resp = client.post('/rentals/refresh')
    assert resp.status_code == 422
    assert resp.json()['success'] is False


def test_refresh_post_broken_mapping_503(api_env):
    (api_env.parent / 'rental_community_mappings.json').write_text(
        'not-json', encoding='utf-8')
    assert client.post('/rentals/refresh').status_code == 503


def test_refresh_delete_cancel_then_conflict(api_env, monkeypatch):
    svc = FakeSvc(job(phase='crawling', running=True, result=None))
    monkeypatch.setattr(rental_routes, '_service', svc)
    resp = client.delete('/rentals/refresh')
    assert resp.status_code == 200
    assert resp.json()['data']['phase'] == 'cancelling'

    monkeypatch.setattr(rental_routes, '_service', FakeSvc())
    idle = FakeSvc(cancel_error=RefreshNotRunning('idle'))
    monkeypatch.setattr(rental_routes, '_service', idle)
    resp = client.delete('/rentals/refresh')
    assert resp.status_code == 409
    assert resp.json()['success'] is False


def test_refresh_post_ignores_arbitrary_params(api_env, monkeypatch):
    """契约：不接受任意上游 URL/输出路径参数（多余 query 被忽略，不 500）。"""
    svc = FakeSvc()
    monkeypatch.setattr(rental_routes, '_service', svc)
    resp = client.post('/rentals/refresh',
                       params={'seed': 'https://evil.example.com', 'out': '/tmp/x'})
    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# phase / last_refresh 纯映射函数
# ---------------------------------------------------------------------------

def test_external_phase_mapping_full_coverage():
    assert _external_phase({'phase': 'crawling', 'result': None}) == 'running'
    assert _external_phase({'phase': 'publishing', 'result': None}) == 'running'
    assert _external_phase({'phase': 'cancelling', 'result': None}) == 'cancelling'
    assert _external_phase({'phase': 'done', 'result': {
        'carried_over': [], 'absent': []}}) == 'succeeded'
    assert _external_phase({'phase': 'done', 'result': None}) == 'succeeded'
    assert _external_phase({'phase': 'done', 'result': {
        'carried_over': ['c'], 'absent': []}}) == 'partial_failed'
    assert _external_phase({'phase': 'done', 'result': {
        'carried_over': [], 'absent': ['a']}}) == 'partial_failed'
    assert _external_phase({'phase': 'failed', 'result': None}) == 'failed'
    assert _external_phase({'phase': 'cancelled', 'result': None}) == 'cancelled'
    assert _external_phase({'phase': 'interrupted', 'result': None}) == 'interrupted'
    assert _external_phase({'phase': 'idle', 'result': None}) == 'idle'


def test_external_job_error_items_shape():
    ext = _external_job(job(errors={'total': 2, 'items': [
        {'stage': 'publish', 'error': 'lock held'}, 'garbage']}))
    assert ext['errors']['items'] == [
        {'community_id': None, 'message': 'lock held'},
        {'community_id': None, 'message': ''}]
    assert ext['errors']['total'] == 2


def test_last_refresh_mapping():
    assert _last_refresh_of(None) is None
    assert _last_refresh_of({'phase': 'idle'}) is None
    assert _last_refresh_of({'job_id': 'j', 'phase': 'crawling'}) == {
        'status': 'running', 'finished_at': None, 'error': None}
    assert _last_refresh_of({'job_id': 'j', 'phase': 'publishing'})['status'] == \
        'running'
    assert _last_refresh_of({'job_id': 'j', 'phase': 'cancelling'})['status'] == \
        'running'
    assert _last_refresh_of({'job_id': 'j', 'phase': 'done',
                             'finished_at': 'T'}) == {
        'status': 'ok', 'finished_at': 'T', 'error': None}
    assert _last_refresh_of({'job_id': 'j', 'phase': 'cancelled',
                             'finished_at': 'T'}) == {
        'status': 'cancelled', 'finished_at': 'T', 'error': None}
    failed = _last_refresh_of({'job_id': 'j', 'phase': 'failed',
                               'finished_at': 'T',
                               'errors': {'items': [{'error': 'boom'}]}})
    assert failed == {'status': 'failed', 'finished_at': 'T', 'error': 'boom'}
    interrupted = _last_refresh_of({'job_id': 'j', 'phase': 'interrupted',
                                    'finished_at': 'T', 'errors': {'items': []}})
    assert interrupted['status'] == 'failed'
    assert interrupted['error'] == 'interrupted by service restart'


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

def test_main_app_registers_rental_routes():
    from src.main import app as main_app
    # 新版 FastAPI include_router 生成嵌套 _IncludedRouter，平铺 route.path
    # 检查不再可靠；openapi schema 展开全部被 include 的路径
    paths = set(main_app.openapi()['paths'].keys())
    assert '/api/rentals/summary' in paths
    assert '/api/rentals/refresh' in paths
    assert '/api/communities/{community_id}/rentals' in paths


def test_shutdown_hook_invokes_service_shutdown(monkeypatch):
    svc = FakeSvc()
    monkeypatch.setattr(rental_routes, '_service', svc)
    asyncio.run(rental_routes.shutdown_rental_refresh())
    assert svc.shutdown_called is True
    monkeypatch.setattr(rental_routes, '_service', None)
    asyncio.run(rental_routes.shutdown_rental_refresh())  # 未创建过服务：无操作


def test_routes_use_shared_group_stats():
    """路由层统计入口与纯函数层共享同一实现（不做重复数学）。"""
    from src.services.rental_reference.statistics import group_stats
    assert rental_routes.group_stats is group_stats
    valid, _audit = rental_routes.select_valid(valid3())
    stats = rental_routes.group_stats(valid, bedrooms=None, band='90to144')
    assert stats['sample_count'] == 3
    assert stats['rent_reference']['median_unit_rent_yuan_m2_month'] == \
        pytest.approx(90.0)
