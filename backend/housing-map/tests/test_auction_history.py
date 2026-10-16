import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services import auction_history as history
from src.api import auction_routes

NOW = datetime(2026, 10, 12, 12, tzinfo=ZoneInfo('Asia/Shanghai'))
COMMUNITIES = [{'community_id': 'c', 'community_name': '小区', 'community_alias': '花园'}]


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch, tmp_path):
    # 名称匹配只在没有 registry 的 legacy 路径生效;真实 data 目录已存在
    # community_registry.sqlite3,不隔离会让本文件所有匹配断言失效。
    monkeypatch.setattr(history, 'MAPPING_PATH', tmp_path / 'auction_community_mappings.json')


def row(aid, **changes):
    return dict(source='laipai', auction_id=str(aid), asset_id=str(aid),
                community_name='花园', status='done', deal_price_yuan=3000000,
                area_m2=100, end_at='2026-09-01 10:00:00', **changes)


def query(rows, **kwargs):
    return history.build_history(rows, COMMUNITIES, {}, 'c', now=NOW, **kwargs)


def test_dedup_statistics_use_all_pages_and_keep_unknown_area():
    rows = [row(1), {**row(2), 'asset_id': '1', 'status': 'failure'},
            {**row(3), 'area_m2': None}, {**row(4), 'deal_price_yuan': 5000000},
            {**row(5), 'end_at': '2030-01-01'}, {**row(6), 'end_at': 'bad'}]
    data = query(rows, page_size=1)
    assert data['total'] == 3 and len(data['records']) == 1
    assert data['stats']['unit_price_sample_count'] == 2
    assert data['stats']['median_unit_price_yuan'] == 40000
    assert data['stats']['min_unit_price_yuan'] == 30000
    assert data['stats']['max_unit_price_yuan'] == 50000
    assert data['stats']['sample_warning']
    assert len(next(r for r in query(rows)['records'] if r['auction_id'] == '1')['rounds']) == 2


def test_latest_sale_before_filter_and_calendar_area_boundaries():
    rows = [row(1), {**row(2), 'asset_id': '1', 'end_at': '2026-10-01', 'area_m2': 144},
            {**row(3), 'end_at': '2025-10-12 12:00:00', 'area_m2': 90},
            {**row(4), 'end_at': '2025-10-12 11:59:59', 'area_m2': 89},
            {**row(5), 'area_m2': None}]
    assert query(rows, area_band='90to144')['total'] == 1
    assert query(rows, area_band='gte144')['total'] == 1
    assert query(rows, area_band='lt90')['total'] == 0
    assert query(rows, period='all')['total'] == 4
    assert history.months_before(datetime(2024, 3, 31, tzinfo=NOW.tzinfo), 1).day == 29


def test_unique_names_conflicts_and_explicit_mapping(tmp_path):
    communities = COMMUNITIES + [{'community_id': 'd', 'community_name': '花园'}]
    assert history.build_history([row(1)], communities, {}, 'c', now=NOW)['total'] == 0
    path = tmp_path / 'mappings.json'
    entry = dict(source='laipai', asset_id='1', community_id='c', note='核验地址')
    path.write_text(json.dumps({'version': 1, 'mappings': [entry]}))
    mappings = history.load_mappings(path, communities)
    assert history.build_history([row(1)], communities, mappings, 'c', now=NOW)['total'] == 1
    for entries in [[entry, entry], [{**entry, 'community_id': 'missing'}]]:
        path.write_text(json.dumps({'version': 1, 'mappings': entries}))
        with pytest.raises(ValueError):
            history.load_mappings(path, communities)


def test_associate_records_legacy_fuzzy_unique_only(tmp_path):
    sole = [{'community_id': 'c', 'community_name': '白金海岸花园'}]
    rows = [{**row(1), 'community_name': '白金海岸花园'}, {**row(2), 'community_name': '白金海岸花园3幢'},
            {**row(3), 'community_name': '康悦名郡3幢'}]
    out = history.associate_records(rows, sole, {}, keep_unmatched=True)
    got = {r['auction_id']: r['community_id'] for r in out}
    assert got['1'] == 'c' and got['2'] == 'c' and got['3'] is None
    ambiguous = sole + [{'community_id': 'd', 'community_name': '白金海岸雅苑'}]
    out = history.associate_records([row(2)], ambiguous, {}, keep_unmatched=True)
    assert out[0]['community_id'] is None


def test_missing_identity_and_invalid_numbers_are_explicit():
    rows = [{**row(1), 'asset_id': None}, {**row(2), 'asset_id': None, 'area_m2': -1},
            {**row(3), 'deal_price_yuan': True}, {**row(4), 'area_m2': float('inf')}]
    data = query(rows)
    assert data['total'] == 3
    assert data['stats']['unit_price_sample_count'] == 1
    assert next(r for r in data['records'] if r['auction_id'] == '1')['identity_warning']
    assert query([])['stats']['median_unit_price_yuan'] is None


def test_property_is_counted_only_in_latest_resolved_community():
    communities = COMMUNITIES + [{'community_id': 'd', 'community_name': '另一小区'}]
    rows = [row(1), {**row(2), 'asset_id': '1', 'community_name': '另一小区', 'end_at': '2026-10-01'}]
    assert history.build_history(rows, communities, {}, 'c', now=NOW)['total'] == 0
    assert history.build_history(rows, communities, {}, 'd', now=NOW)['total'] == 1


def test_unrounded_odd_median_and_half_up_display():
    rows = [{**row(1), 'deal_price_yuan': 1000050},
            {**row(2), 'deal_price_yuan': 2000049},
            {**row(3), 'deal_price_yuan': 3000000}]
    assert query(rows)['stats']['median_unit_price_yuan'] == 20000
    assert query(rows[:1])['stats']['median_unit_price_yuan'] == 10001


def test_mapping_updates_old_records_without_recollection(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'AUCTION_PATH', tmp_path / 'records.json')
    monkeypatch.setattr(history, 'MAPPING_PATH', tmp_path / 'mapping.json')
    monkeypatch.setattr(history, 'load_communities', lambda: COMMUNITIES)
    history.AUCTION_PATH.write_text(json.dumps({'version': 1, 'records': [{**row(1), 'community_name': '不一致名称'}]}))
    assert history.get_history('c', now=NOW)['total'] == 0
    history.MAPPING_PATH.write_text(json.dumps({'version': 1, 'mappings': [{'source': 'laipai', 'auction_id': '1', 'community_id': 'c'}]}))
    assert history.get_history('c', now=NOW)['total'] == 1


def test_history_routes_validate_and_distinguish_missing_store(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'AUCTION_PATH', tmp_path / 'records.json')
    monkeypatch.setattr(history, 'MAPPING_PATH', tmp_path / 'mapping.json')
    monkeypatch.setattr(history, 'load_communities', lambda: COMMUNITIES)
    app = FastAPI()
    app.include_router(auction_routes.router, prefix='/api')
    with TestClient(app) as client:
        assert client.get('/api/communities/c/auction-history').json()['data']['available'] is False
        assert client.get('/api/communities/missing/auction-history').status_code == 404
        assert client.get('/api/communities/c/auction-history?period=bad').status_code == 422
        assert client.get('/api/communities/c/auction-history?page=0').status_code == 422
        history.AUCTION_PATH.write_text(json.dumps({'version': 1, 'records': [row(1)]}))
        result = client.get('/api/auctions/community-summary').json()['data']
        assert result['counts'] == {'c': 1}
        assert result['available'] is True
        history.AUCTION_PATH.write_text('bad')
        assert client.get('/api/communities/c/auction-history').status_code == 503
