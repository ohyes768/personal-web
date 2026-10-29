"""地图侧市场身份与项目证据的 API 契约。

地图要在同一张图上区分新房与二手房, 因此接口必须显式下发房源类型与项目证据:
未知就是未知, 新房不得借用二手价格, 缺坐标的小区照旧不上图但留在目录里。
"""
import json

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.community_registry import CommunityRegistry

client = TestClient(app)

ADDRESS = '杭州市滨江区测试路1号'
COORD = dict(longitude=120.207490, latitude=30.202261)


def _community(store, name, *, source_kind='community', market_state=None, sale_status=None,
               project_id=None, listing_count=3, coordinates=True, coordinate_evidence=None):
    """建一个已收录住宅小区, 并登记一条带市场身份证据的来源。"""
    extra = dict(district='滨江', address=ADDRESS)
    if coordinates:
        extra.update(COORD, coordinate_system='gcj02')
    if coordinate_evidence:
        extra['coordinate_evidence'] = coordinate_evidence
    cid = store.create(name, **extra)['community_id']
    payload = dict(source='tmsf', source_kind=source_kind, source_id=project_id or name,
                   name=name, district='滨江', address=ADDRESS, property_type='住宅',
                   property_type_checked_at='2026-01-01T00:00:00+00:00',
                   address_origin='source_detail', address_checked_at='2026-01-01T00:00:00+00:00')
    if market_state:
        payload['market_state'] = market_state
    if sale_status:
        payload['project_sale_status'] = sale_status
    if project_id:
        payload['project_id'] = project_id
    if listing_count is not None:
        payload['listing_count'] = listing_count
    row = store.ingest(payload)
    store.associate(row['id'], cid)
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    return cid


@pytest.fixture()
def seeded_registry(tmp_path, monkeypatch):
    """带 registry 的最小数据集: 展示链走真实投影路径, 不依赖 data/ 快照。"""
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    ids = {
        'new_house': _community(store, '朗拾滨屿府', source_kind='project', market_state='new_house',
                                sale_status='在售', project_id='2313460053', listing_count=None),
        'sold_out': _community(store, '旧售完项目', source_kind='project', market_state='new_house',
                               sale_status='售完', project_id='2313460054', listing_count=3),
        'second_hand': _community(store, '倾城之恋花园', market_state='second_hand', listing_count=5),
        'unknown': _community(store, '待核实小区'),
        'no_position': _community(store, '无坐标新房', source_kind='project', market_state='new_house',
                                  sale_status='在售', project_id='2313460055', listing_count=None,
                                  coordinates=False),
    }
    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('prepared', '1')")
    for name in ('binjiang_pois.json', 'property_types.json', 'binjiang_polygons_merged.json',
                 'community_ages.json', 'community_attrs.json'):
        (tmp_path / name).write_text(json.dumps({}), encoding='utf-8')
    for name in ('binjiang_transit_routes.geojson', 'binjiang_transit_stops.geojson'):
        (tmp_path / name).write_text(json.dumps({'type': 'FeatureCollection', 'features': []}), encoding='utf-8')
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([]), encoding='utf-8')

    import src.services.data_loader as data_loader

    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    return ids


def _by_name(body):
    return {c['community_name']: c for c in body['data']}


def test_map_records_carry_market_state_and_project_evidence(seeded_registry):
    body = client.get('/api/communities').json()
    records = _by_name(body)

    assert records['朗拾滨屿府']['market_state'] == 'new_house'
    assert records['朗拾滨屿府']['project'] == {
        'project_id': '2313460053',
        'project_name': None,
        'sale_status': '在售',
        'identity_url': None,
        'captured_at': None,
    }
    # 二手房与未知都显式给出类型, 未知不得被默认为二手房
    assert records['倾城之恋花园']['market_state'] == 'second_hand'
    assert records['倾城之恋花园']['project'] is None
    assert records['待核实小区']['market_state'] == 'unknown'


def test_sold_out_project_keeps_evidence_but_reads_as_second_hand(seeded_registry):
    records = _by_name(client.get('/api/communities').json())
    sold = records['旧售完项目']
    assert sold['market_state'] == 'second_hand', '售完按有效状态转入二手房'
    assert sold['project']['sale_status'] == '售完', '历史项目资料不因转入二手而删除'
    assert sold['project']['project_id'] == '2313460054'


def test_new_house_never_borrows_second_hand_price(seeded_registry):
    records = _by_name(client.get('/api/communities').json())
    new_house = records['朗拾滨屿府']
    assert new_house['price'] == {
        'listing_avg_price': None, 'deal_avg_price': None,
        'listing_count': None, 'deal_count': None, 'snapshot_date': '',
    }


def test_new_house_with_existing_price_snapshot_still_shows_no_price(tmp_path, monkeypatch):
    """即��数据里已有二手快照, 新房也不得把它当项目价格下发。"""
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    cid = _community(store, '朗拾滨屿府', source_kind='project', market_state='new_house',
                     sale_status='在售', project_id='2313460053', listing_count=None)
    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('prepared', '1')")
    for name in ('binjiang_pois.json', 'property_types.json', 'binjiang_polygons_merged.json',
                 'community_ages.json', 'community_attrs.json'):
        (tmp_path / name).write_text(json.dumps({}), encoding='utf-8')
    for name in ('binjiang_transit_routes.geojson', 'binjiang_transit_stops.geojson'):
        (tmp_path / name).write_text(json.dumps({'type': 'FeatureCollection', 'features': []}), encoding='utf-8')
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([]), encoding='utf-8')
    # 该小区的二手价格快照确实存在, 且是签约口径
    (tmp_path / 'price_snapshots.jsonl').write_text(json.dumps({
        'community_id': cid, 'community_name': '朗拾滨屿府', 'price_type': 'monthly_deal_avg_latest',
        'avg_price': 38000, 'listing_count': 5, 'deal_count': 2,
        'snapshot_date': '2026-10-01', 'source_url': 'https://www.tmsf.com/esf/xq_indexnew_1.htm',
    }, ensure_ascii=False), encoding='utf-8')

    import src.services.data_loader as data_loader

    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    records = _by_name(client.get('/api/communities').json())
    new_house = records['朗拾滨屿府']
    assert new_house['price']['deal_avg_price'] is None, '新房不得复用二手签约价'
    assert new_house['price']['listing_avg_price'] is None
    assert new_house['price']['deal_count'] is None
    assert new_house['score']['market_score'] is None, '二手成交活跃度不得进入新房评分'


def test_missing_coordinates_stays_out_of_map_but_admitted(seeded_registry):
    body = client.get('/api/communities').json()
    assert '无坐标新房' not in _by_name(body), '缺坐标不伪造项目点'
    assert body['stats']['hidden'].get('missing_coordinates') == 1


def test_position_evidence_reports_manual_and_historical_sources(tmp_path, monkeypatch):
    """人工发布的位置算已核验; 历史快照推导的位置不算, 也不能声称做过新鲜核验。"""
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    manual_id = _community(store, '人工定位小区', coordinate_evidence={'source': 'manual'})
    history_id = _community(store, '历史坐标小区', coordinate_evidence={'source': 'historical_amap'})
    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('prepared', '1')")
    for name in ('binjiang_pois.json', 'property_types.json', 'binjiang_polygons_merged.json',
                 'community_ages.json', 'community_attrs.json'):
        (tmp_path / name).write_text(json.dumps({}), encoding='utf-8')
    for name in ('binjiang_transit_routes.geojson', 'binjiang_transit_stops.geojson'):
        (tmp_path / name).write_text(json.dumps({'type': 'FeatureCollection', 'features': []}), encoding='utf-8')
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([]), encoding='utf-8')

    import src.services.data_loader as data_loader

    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    records = _by_name(client.get('/api/communities').json())
    assert records['人工定位小区']['position']['verified'] is True
    assert records['人工定位小区']['position']['source'] == 'manual'
    assert records['历史坐标小区']['position']['verified'] is False
    assert records['历史坐标小区']['position']['source'] == 'historical_amap'


def test_conflicting_market_evidence_is_flagged(tmp_path, monkeypatch):
    """新房与二手证据并存时保留冲突标记, 不静默取一个。"""
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    cid = store.create('混合市场小区', district='滨江', address=ADDRESS, **COORD,
                       coordinate_system='gcj02')['community_id']
    esf = store.ingest(dict(source='tmsf', source_kind='community', source_id='c1', name='混合市场小区',
                            district='滨江', market_state='second_hand', listing_count=5,
                            property_type='住宅', property_type_checked_at='2026-01-01T00:00:00+00:00',
                            address=ADDRESS, address_origin='source_detail',
                            address_checked_at='2026-01-01T00:00:00+00:00'))
    project = store.ingest(dict(source='tmsf', source_kind='project', source_id='2313460056',
                                name='混合市场小区', district='滨江', market_state='new_house',
                                project_id='2313460056', project_sale_status='在售', property_type='住宅',
                                property_type_checked_at='2026-01-01T00:00:00+00:00', address=ADDRESS,
                                address_origin='source_detail', address_checked_at='2026-01-01T00:00:00+00:00'))
    store.associate(esf['id'], cid)
    store.associate(project['id'], cid)
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('prepared', '1')")
    for name in ('binjiang_pois.json', 'property_types.json', 'binjiang_polygons_merged.json',
                 'community_ages.json', 'community_attrs.json'):
        (tmp_path / name).write_text(json.dumps({}), encoding='utf-8')
    for name in ('binjiang_transit_routes.geojson', 'binjiang_transit_stops.geojson'):
        (tmp_path / name).write_text(json.dumps({'type': 'FeatureCollection', 'features': []}), encoding='utf-8')
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([]), encoding='utf-8')

    import src.services.data_loader as data_loader

    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    records = _by_name(client.get('/api/communities').json())
    assert records['混合市场小区']['market_state'] == 'new_house'
    assert records['混合市场小区']['market_state_conflict'] is True
