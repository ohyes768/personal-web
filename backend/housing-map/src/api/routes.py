"""API 路由

移植自源项目 web/src/app/api/{communities,score,transit,refresh}/route.ts。
响应结构与字段名与源 Next.js 完全一致（design D8）。
"""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.api.models import MOCK_COMMUNITIES, RefreshLimit, ScoreWeights
from src.services import boundary_refresh
from src.services import refresh as refresh_service
from src.services.community_filters import is_real_community
from src.services.market_reference import load_market_reference
from src.services.data_loader import (
    get_data_paths,
    load_communities,
    load_community_attrs,
    load_community_ages,
    load_coordinates,
    load_json,
    load_pois,
    load_polygons,
    load_price_snapshots,
    load_property_types,
    load_subway_stations,
    load_transit_routes,
    load_transit_stops,
)
from src.services.scoring import DEFAULT_WEIGHTS, calculate_score, find_nearest_station, js_round
from src.services.transit import boundary_points, build_subway_data

router = APIRouter()

# 水电片区: tmsf 以新旧名重复收录 5 个条目(同一片区), 合并为单条展示。
# 价格/POI 借用有数据的成员(西兴镇水电社区: 挂牌 35127 可信;
# 一区 9937/三区 4549 为 0 签约下的异常签约价, 不采用)
COMMUNITY_MERGE_GROUPS = [
    {
        "primaryId": "453982737",   # 水电社区(保留)
        "fallbackId": "453982238",  # 西兴镇水电社区(价格/POI 来源)
        "dropIds": ["453982238", "20073231", "5001850", "20056022"],  # 西兴镇水电社区/省水电新村一区/二区/三区
    },
]
MERGE_DROP_IDS = {did for g in COMMUNITY_MERGE_GROUPS for did in g["dropIds"]}


# ---------------------------------------------------------------------------
# 组装工具（/communities 与 /score 共用; 差异通过参数控制, 行为与源两份 route.ts 一致）
# ---------------------------------------------------------------------------

def _poi_list_of(pois: dict) -> list[dict]:
    """{type: [poi...]} 展平为 POI 数组"""
    poi_list: list[dict] = []
    for poi_type, items in pois.items():
        for item in items:
            poi_list.append({
                "name": item["name"],
                "type": poi_type,
                "distance": item["distance"],
                "latitude": item["latitude"],
                "longitude": item["longitude"],
            })
    return poi_list


def _parking_ratio_of(community_attrs: dict, cid) -> float | None:
    """车位比 = 车位数/总户数 (两者都有正数才有效)"""
    a = community_attrs.get(cid)
    if not a or not a.get("parking_spots") or not a.get("households"):
        return None
    return js_round((a["parking_spots"] / a["households"]) * 100) / 100


def _nearest_subway_of(coordinates: dict, cid, subway_stations: list) -> dict | None:
    coord = coordinates.get(cid)
    if coord and coord.get("latitude") and coord.get("longitude"):
        return find_nearest_station(subway_stations, coord["longitude"], coord["latitude"])
    return None


def _assemble_community(
    c: dict,
    *,
    coordinates: dict,
    pois_block: dict,
    price_data: dict | None,
    subway_stations: list,
    community_ages: dict,
    community_attrs: dict,
    property_types: dict | None = None,  # None -> 不输出 property_type (score 路由)
    polygons: dict | None = None,        # None -> 不输出 boundary/boundary_source (score 路由)
    include_counts: bool = True,         # False -> listing_count/deal_count 固定 null (score 路由)
) -> dict:
    """组装单条 Community 记录（未评分, score 置零占位）"""
    cid = c.get("community_id")
    coord = coordinates.get(cid)
    pois = pois_block.get("pois") or {}
    # 签约均价 -> deal_avg_price, 挂牌样本均价 -> listing_avg_price
    is_deal_price = (price_data or {}).get("price_type") == "monthly_deal_avg_latest"
    price_val = price_data.get("price") if price_data else None

    record: dict = {
        "community_id": cid,
        "community_name": c.get("community_name"),
        "district": c.get("district"),
        "subdistrict": c.get("subdistrict"),
        "address": c.get("address") or "",
        "latitude": (coord or {}).get("latitude") or 0,
        "longitude": (coord or {}).get("longitude") or 0,
        "price": {
            "listing_avg_price": None if is_deal_price else price_val,
            "deal_avg_price": price_val if is_deal_price else None,
            # 注意保 0 而非吞 null: 0 是有效数据(如"签约0套"应得市场面30分)
            "listing_count": (price_data.get("listing_count") if price_data else None) if include_counts else None,
            "deal_count": (price_data.get("deal_count") if price_data else None) if include_counts else None,
            "snapshot_date": (price_data.get("date") or "") if price_data else "",
        },
        "pois": _poi_list_of(pois),
        "score": {
            "total_score": 0,
            "location_score": None,
            "product_score": None,
            "amenity_score": None,
            "market_score": None,
        },
    }

    # TS: property_type ?? undefined -> JSON 序列化时省略该键
    if property_types is not None:
        prop_type_data = property_types.get(cid)
        prop_type = prop_type_data.get("property_type") if prop_type_data else None
        if prop_type is not None:
            record["property_type"] = prop_type

    if polygons is not None:
        poly = polygons.get(cid)
        if poly is not None:
            if "rings" in poly:
                record["boundary"] = poly["rings"]
            if "source" in poly:
                record["boundary_source"] = poly["source"]

    record["build_year"] = (community_ages.get(cid) or {}).get("build_year")
    record["parking_ratio"] = _parking_ratio_of(community_attrs, cid)
    record["property_fee"] = (community_attrs.get(cid) or {}).get("property_fee")
    record["far_ratio"] = (community_attrs.get(cid) or {}).get("far_ratio")
    record["greening_rate"] = (community_attrs.get(cid) or {}).get("greening_rate")
    record["nearest_subway"] = _nearest_subway_of(coordinates, cid, subway_stations)
    return record


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/health", tags=["system"])
async def health():
    """健康检查"""
    return {"status": "ok"}


@router.get("/market-reference")
async def get_market_reference():
    """返回人工校验的挂牌参考行情，不参与小区价格或评分。"""
    snapshot = load_market_reference()
    return {"success": True, "data": snapshot}


@router.get("/communities")
async def get_communities():
    property_types = load_property_types()
    communities_list = [
        c for c in load_communities()
        if is_real_community(c)
        and c.get("community_id") not in MERGE_DROP_IDS
    ]
    coordinates = load_coordinates()
    pois_data = load_pois()
    polygons = load_polygons()
    subway_stations = load_subway_stations()
    community_ages = load_community_ages()
    community_attrs = load_community_attrs()
    transit_routes = load_transit_routes()
    transit_stops = load_transit_stops()

    # 合并组: 主条目缺价格时借用 fallback 成员的数据(不可变复制, 不污染加载结果)
    price_snapshots = dict(load_price_snapshots())
    for g in COMMUNITY_MERGE_GROUPS:
        if g["primaryId"] not in price_snapshots and g["fallbackId"] in price_snapshots:
            price_snapshots[g["primaryId"]] = price_snapshots[g["fallbackId"]]

    def pois_of(cid):
        if cid in pois_data:
            return pois_data[cid]
        g = next((g for g in COMMUNITY_MERGE_GROUPS if g["primaryId"] == cid), None)
        if g is not None and g["fallbackId"] in pois_data:
            return pois_data[g["fallbackId"]]
        return {"pois": {}}

    if len(communities_list) == 0:
        return {
            "success": True,
            "data": MOCK_COMMUNITIES,
            "total": len(MOCK_COMMUNITIES),
            "source": "mock",
        }

    data = [
        _assemble_community(
            c,
            coordinates=coordinates,
            pois_block=pois_of(c.get("community_id")),
            price_data=price_snapshots.get(c.get("community_id")),
            subway_stations=subway_stations,
            community_ages=community_ages,
            community_attrs=community_attrs,
            property_types=property_types,
            polygons=polygons,
        )
        for c in communities_list
    ]
    data_with_scores = [{**rec, "score": calculate_score(rec)} for rec in data]

    # transit 为原始 GeoJSON FeatureCollection (未裁剪; 前端实际用 /api/transit 的裁剪版)
    return {
        "success": True,
        "data": data_with_scores,
        "total": len(data_with_scores),
        "source": "real",
        "transit": {"routes": transit_routes, "stops": transit_stops},
    }


@router.get("/score")
async def get_score(
    id: str | None = Query(None),
    locationWeight: int | None = Query(None),  # noqa: N803 (与源 query 参数名一致)
    amenityWeight: int | None = Query(None),  # noqa: N803
    productWeight: int | None = Query(None),  # noqa: N803
    marketWeight: int | None = Query(None),  # noqa: N803
):
    # 从查询参数获取权重 (价格不参与评分)
    weights = ScoreWeights(
        location=locationWeight if locationWeight is not None else DEFAULT_WEIGHTS["location"],
        amenity=amenityWeight if amenityWeight is not None else DEFAULT_WEIGHTS["amenity"],
        product=productWeight if productWeight is not None else DEFAULT_WEIGHTS["product"],
        market=marketWeight if marketWeight is not None else DEFAULT_WEIGHTS["market"],
    ).model_dump()

    # 加载数据
    communities = load_communities()
    coordinates = load_coordinates()
    pois_data = load_pois()
    price_snapshots = load_price_snapshots()
    subway_stations = load_subway_stations()
    community_ages = load_community_ages()
    community_attrs = load_community_attrs()

    if not communities:
        return {"success": False, "error": "没有可用的小区数据"}

    def build(community: dict) -> dict:
        cid = community.get("community_id")
        rec = _assemble_community(
            community,
            coordinates=coordinates,
            pois_block=pois_data.get(cid) or {"pois": {}},
            price_data=price_snapshots.get(cid),
            subway_stations=subway_stations,
            community_ages=community_ages,
            community_attrs=community_attrs,
            include_counts=False,  # 单小区模式 listing_count/deal_count 固定 null
        )
        return {**rec, "score": calculate_score(rec, weights)}

    # 单个小区评分
    if id:
        community = next((c for c in communities if c.get("community_id") == id), None)
        if community is None:
            return {"success": False, "error": "找不到指定的小区"}
        return {"success": True, "data": build(community)}

    # 批量评分, 按总分排序
    results = [build(community) for community in communities]
    results.sort(key=lambda r: r["score"]["total_score"], reverse=True)

    return {"success": True, "data": results, "total": len(results), "weights": weights}


@router.get("/transit")
async def get_transit():
    paths = get_data_paths()
    # TS loadGeoJson: 文件缺失/解析失败返回 null
    routes_geo = load_json(paths["transit_routes"], None)
    stops_geo = load_json(paths["transit_stops"], None)

    subway_routes, subway_stops = build_subway_data(routes_geo, stops_geo)

    return {
        "success": True,
        "data": {"routes": subway_routes, "stops": subway_stops},
        "meta": {
            "route_count": len(subway_routes),
            "stop_count": len(subway_stops),
            "boundary_points": boundary_points(),
        },
    }


@router.get("/refresh")
async def get_refresh_status():
    return {"success": True, "data": refresh_service.job}


@router.post("/refresh")
async def start_refresh_job(params: Annotated[RefreshLimit, Query()]):
    _, status, body = await refresh_service.start_refresh(params.limit)
    return JSONResponse(status_code=status, content=body)


@router.delete("/refresh")
async def stop_refresh_job():
    _, status, body = await refresh_service.stop_refresh()
    return JSONResponse(status_code=status, content=body)


@router.get("/boundaries/rebuild")
async def get_boundary_rebuild_status():
    return {"success": True, "data": boundary_refresh.job}


@router.post("/boundaries/rebuild")
async def start_boundary_rebuild_job():
    _, status, body = await boundary_refresh.start_rebuild()
    return JSONResponse(status_code=status, content=body)
