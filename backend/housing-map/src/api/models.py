"""API 入参模型与兜底数据

响应体一律用 dict 直传（字段名与源 Next.js 完全一致, 含 camelCase — design D8）,
强类型仅用于入参。
"""

from pydantic import BaseModel


class ScoreWeights(BaseModel):
    """评分权重覆盖（默认 30/30/25/15, 价格不参与评分）"""

    location: int = 30
    amenity: int = 30
    product: int = 25
    market: int = 15


class RefreshLimit(BaseModel):
    """refresh 测试限量（?limit=N, 0=全量; 上限 500 由服务端 clamp）"""

    limit: int = 0


# 预设小区数据（源 types.ts MOCK_COMMUNITIES 原样移植）:
# 仅 communities API 空数据兜底用, source 返回 "mock"
MOCK_COMMUNITIES: list[dict] = [
    {
        "community_id": "20044031",
        "community_name": "万科璞悦湾",
        "district": "滨江区",
        "subdistrict": "浦沿",
        "address": "滨文路与浦沿路交叉口",
        "latitude": 30.1749,
        "longitude": 120.1785,
        "price": {
            "listing_avg_price": 40659,
            "deal_avg_price": 38500,
            "listing_count": 23,
            "deal_count": 5,
            "snapshot_date": "2026-05-08",
        },
        "pois": [
            {"name": "浦沿站", "type": "subway", "distance": 350, "latitude": 30.1755, "longitude": 120.1790},
            {"name": "江南实验小学", "type": "school", "distance": 800, "latitude": 30.1730, "longitude": 120.1770},
            {"name": "龙湖天街", "type": "mall", "distance": 1200, "latitude": 30.1700, "longitude": 120.1800},
        ],
        "score": {"total_score": 78, "location_score": None, "amenity_score": 82, "product_score": None, "market_score": None},
    },
    {
        "community_id": "10001734",
        "community_name": "世茂之西湖",
        "district": "滨江区",
        "subdistrict": "浦沿",
        "address": "浦沿街道世茂之西湖小区",
        "latitude": 30.1812,
        "longitude": 120.1856,
        "price": {
            "listing_avg_price": 47880,
            "deal_avg_price": 45200,
            "listing_count": 18,
            "deal_count": 3,
            "snapshot_date": "2026-05-08",
        },
        "pois": [
            {"name": "中医药大学站", "type": "subway", "distance": 500, "latitude": 30.1820, "longitude": 120.1860},
            {"name": "滨江实验中学", "type": "school", "distance": 1000, "latitude": 30.1790, "longitude": 120.1840},
            {"name": "星光大道", "type": "mall", "distance": 800, "latitude": 30.1800, "longitude": 120.1830},
        ],
        "score": {"total_score": 82, "location_score": None, "amenity_score": 85, "product_score": None, "market_score": None},
    },
    {
        "community_id": "10001735",
        "community_name": "世茂之西湖茂御居",
        "district": "滨江区",
        "subdistrict": "浦沿",
        "address": "浦沿街道茂御居",
        "latitude": 30.1820,
        "longitude": 120.1862,
        "price": {
            "listing_avg_price": 13290,
            "deal_avg_price": 12800,
            "listing_count": 45,
            "deal_count": 12,
            "snapshot_date": "2026-05-08",
        },
        "pois": [
            {"name": "中医药大学站", "type": "subway", "distance": 450, "latitude": 30.1825, "longitude": 120.1865},
            {"name": "浦沿中心幼儿园", "type": "school", "distance": 600, "latitude": 30.1830, "longitude": 120.1850},
            {"name": "江南时代", "type": "mall", "distance": 900, "latitude": 30.1810, "longitude": 120.1870},
        ],
        "score": {"total_score": 65, "location_score": None, "amenity_score": 70, "product_score": None, "market_score": None},
    },
]
