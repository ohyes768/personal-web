"""构造新房/二手房混合的隔离数据集, 供地图端到端验证使用。

只在隔离目录运行: 不读也不写生产 data/。覆盖 PRD 的关键分支:
有价/无价新房、在售/待售/售完、未知类型、已核验/待核验位置、缺坐标、
近处/远处的二手与无价二手。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.community_registry import CommunityRegistry

ADDRESS = '杭州市滨江区测试路1号'
# 滨江测试点位 (围栏内)
COORD = dict(longitude=120.207490, latitude=30.202261)
NEARBY_COORD = dict(longitude=120.210000, latitude=30.204000)   # 约 300m
FAR_COORD = dict(longitude=120.230000, latitude=30.230000)       # 约 3km, 应落在半径外


def build(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    store = CommunityRegistry(target / 'community_registry.sqlite3')
    ids: dict[str, str] = {}
    source_ids: dict[str, str] = {}

    def community(key, name, *, source_kind='community', market_state=None, sale_status=None,
                  project_id=None, listing_count=3, coord=None, evidence=None):
        extra = dict(district='滨江', address=ADDRESS)
        if coord:
            extra.update(coord, coordinate_system='gcj02')
        if evidence:
            extra['coordinate_evidence'] = evidence
        cid = store.create(name, community_id=f'local-{key}', **extra)['community_id']
        # 价格快照按来源 source_id 关联到小区 (registry 模式下 load_price_snapshots
        # 走 sources 映射), 所以 source_id 要与快照行里的 community_id 一致
        source_id = f'sid-{key}'
        payload = dict(source='tmsf', source_kind=source_kind, source_id=source_id,
                       name=name, district='滨江', address=ADDRESS, property_type='住宅',
                       property_type_checked_at='2026-10-01T00:00:00+00:00',
                       address_origin='source_detail', address_checked_at='2026-10-01T00:00:00+00:00')
        if market_state:
            payload['market_state'] = market_state
        if sale_status:
            payload['project_sale_status'] = sale_status
        if project_id:
            payload['project_id'] = project_id
        if listing_count is not None:
            payload['listing_count'] = listing_count
        if evidence:
            payload['coordinate_evidence'] = evidence
        row = store.ingest(payload)
        store.associate(row['id'], cid)
        store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
        ids[key] = cid
        source_ids[key] = source_id
        return cid

    # 在售新房: 位置已核验(实心), 有项目身份
    community('newhouse', '朗拾滨屿府', source_kind='project', market_state='new_house',
              sale_status='在售', project_id='2313460053', listing_count=None, coord=COORD,
              evidence=dict(source='amap', source_id='amap-1', captured_at='2026-10-01T00:00:00+00:00'))
    # 待售新房: 位置待核验(空心), 无项目名
    community('newhouse-pending', '待售新盘', source_kind='project', market_state='new_house',
              sale_status='待售', project_id='2313460054', listing_count=None, coord=NEARBY_COORD,
              evidence=dict(source='historical_amap', source_id='hist-1'))
    # 缺坐标新房: 不应上图
    community('newhouse-nocoord', '缺坐标新盘', source_kind='project', market_state='new_house',
              sale_status='在售', project_id='2313460055', listing_count=None, coord=None)
    # 售完项目: 有效状态转为二手房, 保留项目资料
    community('soldout', '旧售完项目', source_kind='project', market_state='new_house',
              sale_status='售完', project_id='2313460056', listing_count=4, coord=COORD)
    # 二手房: 近处有价 / 近处无价 / 远处有价
    community('second-near', '近处有价二手', market_state='second_hand', listing_count=6, coord=NEARBY_COORD)
    community('second-noprice', '近处无价二手', market_state='second_hand', listing_count=5, coord=NEARBY_COORD)
    community('second-far', '远处有价二手', market_state='second_hand', listing_count=9, coord=FAR_COORD)
    # 未知类型: 只在「全部」出现
    community('unknown', '类型待核实小区', coord=COORD)

    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('prepared', '1')")

    (target / 'binjiang_communities.json').write_text(json.dumps([], ensure_ascii=False), encoding='utf-8')
    (target / 'binjiang_coordinates.json').write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
    (target / 'binjiang_pois.json').write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
    (target / 'property_types.json').write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
    (target / 'binjiang_polygons_merged.json').write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
    (target / 'community_ages.json').write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
    (target / 'community_attrs.json').write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
    for name in ('binjiang_transit_routes.geojson', 'binjiang_transit_stops.geojson'):
        (target / name).write_text(json.dumps({'type': 'FeatureCollection', 'features': []}), encoding='utf-8')
    # 价格快照: 近处有价二手 / 远处有价二手; 新房社区也放一份, 验证新房不借用二手价格
    # 签约口径要求 raw_payload.tendency.latest_month 与 snapshot_date 同月或更近
    rows = [
        dict(community_id=source_ids['second-near'], community_name='近处有价二手',
             price_type='monthly_deal_avg_latest', avg_price=42000, listing_count=6, deal_count=3,
             snapshot_date='2026-10-20', source_url='https://www.tmsf.com/esf/xq_indexnew_1.htm',
             raw_payload=dict(tendency=dict(latest_month='2026-10'))),
        dict(community_id=source_ids['second-far'], community_name='远处有价二手',
             price_type='listing_avg', avg_price=36000, listing_count=9, deal_count=0,
             snapshot_date='2026-10-20', source_url='https://www.tmsf.com/esf/xq_indexnew_2.htm'),
        dict(community_id=source_ids['newhouse'], community_name='朗拾滨屿府',
             price_type='monthly_deal_avg_latest', avg_price=52000, listing_count=4, deal_count=1,
             snapshot_date='2026-10-20', source_url='https://www.tmsf.com/esf/xq_indexnew_3.htm',
             raw_payload=dict(tendency=dict(latest_month='2026-10'))),
    ]
    (target / 'price_snapshots.jsonl').write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    print(f'seeded {target}')
    print('ids:', json.dumps(ids, ensure_ascii=False))
    print('source_ids:', json.dumps(source_ids, ensure_ascii=False))


if __name__ == '__main__':
    build(Path(sys.argv[1]))
