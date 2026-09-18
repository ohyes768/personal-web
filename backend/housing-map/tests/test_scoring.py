"""scoring 模块测试: 四维公式逐项对齐源 scoring.ts

公式断言值均由源公式手算得出, 用于保证移植后与 Next.js 版评分结果一致。
"""

from datetime import datetime

from src.services.scoring import (
    calculate_all_scores,
    calculate_amenity_score,
    calculate_location_score,
    calculate_market_score,
    calculate_product_score,
    calculate_score,
    find_nearest_station,
    get_school_level,
)


# ---------------------------------------------------------------------------
# 区位
# ---------------------------------------------------------------------------

def test_location_400m_boundary():
    # ≤400m 段: 100 - d*0.025; d=400 恰在段内 → 90
    assert calculate_location_score(400) == 90
    assert calculate_location_score(0) == 100
    assert calculate_location_score(200) == 95


def test_location_decay_segment():
    # >400m 段: max(20, 90-(d-400)/30); d=401 → 89.97 → 90; 2500 → 20; 超出保底 20
    assert calculate_location_score(401) == 90
    assert calculate_location_score(2500) == 20
    assert calculate_location_score(2501) == 20  # 保底 20, 不会更低


def test_location_none():
    assert calculate_location_score(None) is None


# ---------------------------------------------------------------------------
# 配套
# ---------------------------------------------------------------------------

def test_amenity_empty_is_none():
    assert calculate_amenity_score([]) is None


def test_amenity_all_types_absent_fixed_10():
    # 有 POI 但五类设施全缺 (只有 subway, 地铁归区位不计配套) → 每类固定 10 分
    pois = [{"name": "西浦路站", "type": "subway", "distance": 200, "latitude": 30.17, "longitude": 120.13}]
    assert calculate_amenity_score(pois) == 10


def _pois_with_schools(*schools):
    """构造只含 school 一类 + 其他四类缺席的 POI 列表"""
    pois = [{"name": n, "type": "school", "distance": d, "latitude": 30.17, "longitude": 120.13}
            for n, d in schools]
    return pois


def test_amenity_school_distance_divided_by_14():
    # 小学 ÷1.4: 1400m → 折算 1000m → (20 + 40-1000/30)*0.35 + 10*(0.2+0.2+0.15+0.1)
    #           = (20+6.6667)*0.35 + 6.5 = 15.833 → 16
    assert calculate_amenity_score(_pois_with_schools(("江南实验小学", 1400))) == 16


def test_amenity_university_distance_divided_by_06():
    # 大学 ÷0.6: 600m → 折算 1000m → 与小学例同值 16
    assert calculate_amenity_score(_pois_with_schools(("浙江XX大学", 600))) == 16


def test_amenity_count_capped_at_3():
    # countScore = min(count*20, 60): 3 个封顶 → 4 个与 3 个同分
    three = _pois_with_schools(("A小学", 500), ("B小学", 600), ("C小学", 700))
    four = three + [{"name": "D小学", "type": "school", "distance": 800, "latitude": 30.17, "longitude": 120.13}]
    assert calculate_amenity_score(three) == calculate_amenity_score(four)


# ---------------------------------------------------------------------------
# 产品力
# ---------------------------------------------------------------------------

def test_product_all_missing_is_none():
    assert calculate_product_score(None, None, None, None, None) is None


def test_product_single_parts():
    current_year = datetime.now().year
    # 当年建成 → 楼龄 0 → 100
    assert calculate_product_score(current_year, None, None, None, None) == 100
    # 楼龄保底 30
    assert calculate_product_score(1900, None, None, None, None) == 30
    # 车位比 0.8 → 35+40=75
    assert calculate_product_score(None, 0.8, None, None, None) == 75
    # 容积率 1.0 → 100
    assert calculate_product_score(None, None, None, 1.0, None) == 100
    # 物业费 2 元 → 45+30=75
    assert calculate_product_score(None, None, 2.0, None, None) == 75
    # 绿化率 30% → 30+48=78
    assert calculate_product_score(None, None, None, None, 30) == 78


def test_product_missing_parts_renormalized():
    # 只有两子项: 楼龄 100(w35) + 车位比 75(w20) → (3500+1500)/55 = 90.9 → 91
    current_year = datetime.now().year
    assert calculate_product_score(current_year, 0.8, None, None, None) == 91


# ---------------------------------------------------------------------------
# 市场面
# ---------------------------------------------------------------------------

def test_market_zero_deals_is_30():
    # 0 套是有效数据 → 30 分 (不能吞成 null)
    assert calculate_market_score(0) == 30


def test_market_none():
    assert calculate_market_score(None) is None


def test_market_js_round_half_up():
    # deal=3 → 35+19.5=54.5 → JS Math.round=55 (Python 内建 round 会给 54, 回归哨兵)
    assert calculate_market_score(3) == 55


def test_market_capped_95():
    assert calculate_market_score(10) == 95


# ---------------------------------------------------------------------------
# 最近地铁站
# ---------------------------------------------------------------------------

def test_find_nearest_station():
    stations = [
        {"name": "远站", "longitude": 120.001, "latitude": 30.0},
        {"name": "近站", "longitude": 120.0, "latitude": 30.0},
    ]
    nearest = find_nearest_station(stations, 120.0, 30.0)
    assert nearest == {"name": "近站", "distance": 0}


def test_find_nearest_station_empty():
    assert find_nearest_station([], 120.0, 30.0) is None


# ---------------------------------------------------------------------------
# 学段推断 (折算系数依赖)
# ---------------------------------------------------------------------------

def test_get_school_level():
    assert get_school_level("滨兰实验幼儿园") == "kindergarten"
    assert get_school_level("江南实验小学") == "primary"
    assert get_school_level("滨江实验中学") == "middle"
    assert get_school_level("杭州第二中学") == "middle"
    assert get_school_level("浙江XX大学") == "university"
    assert get_school_level("XX编程培训机构") is None
    # "二中"不含源词表任何 token, 与 TS 一致返回 None
    assert get_school_level("杭州二中") is None


# ---------------------------------------------------------------------------
# 综合评分
# ---------------------------------------------------------------------------

def _community(**overrides):
    base = {
        "community_id": "1",
        "community_name": "测试小区",
        "price": {"deal_count": None},
        "pois": [],
        "nearest_subway": None,
        "build_year": None,
        "parking_ratio": None,
        "property_fee": None,
        "far_ratio": None,
        "greening_rate": None,
    }
    base.update(overrides)
    return base


def test_score_all_dimensions_missing_is_50():
    # 全维度无数据 → weightSum=0 → 固定 50
    assert calculate_score(_community())["total_score"] == 50


def test_score_renormalizes_missing_dimensions():
    # 仅市场面有分 (deal=10 → 95) → 权重重归一 → 总分 95
    score = calculate_score(_community(price={"deal_count": 10}))
    assert score["total_score"] == 95
    assert score["market_score"] == 95
    assert score["location_score"] is None


def test_score_full_dimensions():
    # 区位 400m→90, 配套全缺→10, 产品力当年楼→100, 市场 0 套→30
    # 总分 = (90*30 + 10*30 + 100*25 + 30*15) / 100 = 59.5 → 60
    score = calculate_score(_community(
        nearest_subway={"name": "西浦路站", "distance": 400},
        pois=[{"name": "西浦路站", "type": "subway", "distance": 200, "latitude": 30.17, "longitude": 120.13}],
        build_year=datetime.now().year,
        price={"deal_count": 0},
    ))
    assert score == {
        "total_score": 60,
        "location_score": 90,
        "amenity_score": 10,
        "product_score": 100,
        "market_score": 30,
    }


def test_score_clamped_to_0_100():
    # deal 巨大 → market 封顶 95, 单维权重 → 总分 95, 不越界
    score = calculate_score(_community(price={"deal_count": 1000}))
    assert 0 <= score["total_score"] <= 100


def test_calculate_all_scores_preserves_fields():
    communities = [_community(community_id="a"), _community(community_id="b", price={"deal_count": 5})]
    scored = calculate_all_scores(communities)
    assert scored[0]["community_id"] == "a"
    assert "score" in scored[0] and "score" in scored[1]
