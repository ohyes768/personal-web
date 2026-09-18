"""评分计算

移植自源项目 web/src/lib/scoring.ts，四维公式逐行对齐。
关键差异防护: JS Math.round 是"四舍五入向 +∞"，Python round 是银行家舍入
（round(88.5)=88 vs JS 89），分数场景会产出不同整数，因此统一走 js_round。
"""

import math
import re
from datetime import datetime

# 地铁站最近距离计算用常数 (纬度换算)
M_PER_DEG_LAT = 111320


def js_round(x: float) -> int:
    """模拟 JS Math.round (半数向 +∞ 进位)"""
    return int(math.floor(x + 0.5))


# ---------------------------------------------------------------------------
# 学校学段推断（移植自 types.ts，评分折算依赖）
# ---------------------------------------------------------------------------

def get_school_level(name: str) -> str | None:
    """从学校名称推断学段; None 表示培训机构/文化设施等噪音。

    九年一贯制/职业学校/专修学校归入中学段。
    """
    if re.search(r"幼儿园|幼托|托育|学前教育|分园|幼幼|托崽", name):
        return "kindergarten"
    if re.search(r"小学", name):
        return "primary"
    if re.search(r"大学|学院|研究院|校区|院校", name):
        return "university"
    if re.search(
        r"中学|初中|高中|初级|高级|实验|九年|一贯|职业|专修|中专|技校|学校|school",
        name,
        re.IGNORECASE,
    ):
        return "middle"
    return None


# ---------------------------------------------------------------------------
# 最近地铁站
# ---------------------------------------------------------------------------

def find_nearest_station(
    stations: list[dict], lon: float, lat: float
) -> dict | None:
    """找直线距离最近的地铁站 (米)"""
    best: dict | None = None
    for s in stations:
        dx = (s["longitude"] - lon) * M_PER_DEG_LAT * math.cos((lat * math.pi) / 180)
        dy = (s["latitude"] - lat) * M_PER_DEG_LAT
        dist = js_round(math.hypot(dx, dy))
        if best is None or dist < best["distance"]:
            best = {"name": s["name"], "distance": dist}
    return best


# 默认评分权重 (价格不参与评分: 价格是筛选条件而非居住质量)
DEFAULT_WEIGHTS = {"location": 30, "amenity": 30, "product": 25, "market": 15}

# 配套类设施缺席时的固定分: 低于任何"有设施"情形的得分, 保证"无"不会倒挂"有但远"
FACILITY_ABSENT_SCORE = 10

# 配套类型权重 (地铁归区位维度, 不在此重复计分)
AMENITY_TYPE_WEIGHTS = {
    "school": 0.35,
    "hospital": 0.20,
    "mall": 0.20,
    "park": 0.15,
    "bus": 0.10,
}


# ---------------------------------------------------------------------------
# 四维得分
# ---------------------------------------------------------------------------

def calculate_location_score(subway_distance: float | None) -> int | None:
    """区位价值得分: 最近地铁站直线距离
    (400m 步行圈内 90-100, 线性衰减, 2500m 外保底 20)"""
    if subway_distance is None:
        return None
    if subway_distance <= 400:
        return js_round(100 - subway_distance * 0.025)
    return js_round(max(20, 90 - (subway_distance - 400) / 30))


def _school_importance(name: str) -> float:
    """学段重要性系数: 小学/中学 1.4 > 幼儿园 1.0 > 大学 0.6
    折算距离 = 实际距离 / 系数, 系数越高折算越近、对得分贡献越大"""
    level = get_school_level(name)
    if level in ("primary", "middle"):
        return 1.4
    if level == "university":
        return 0.6
    return 1.0


def calculate_amenity_score(pois: list[dict]) -> int | None:
    """配套得分: 教育/医疗/商业/公园/公交的数量与最近距离"""
    if len(pois) == 0:
        return None

    pois_by_type: dict[str, list[dict]] = {}
    for poi in pois:
        pois_by_type.setdefault(poi["type"], []).append(poi)

    total_score = 0.0
    total_weight = 0.0
    for poi_type, weight in AMENITY_TYPE_WEIGHTS.items():
        type_pois = pois_by_type.get(poi_type) or []
        if len(type_pois) == 0:
            total_score += FACILITY_ABSENT_SCORE * weight
        else:
            if poi_type == "school":
                # 学段折算最近距离
                nearest_dist = min(p["distance"] / _school_importance(p["name"]) for p in type_pois)
            else:
                nearest_dist = min(p["distance"] for p in type_pois)
            count_score = min(len(type_pois) * 20, 60)  # 3 个封顶
            distance_score = max(0.0, 40 - nearest_dist / 30)  # 0m→40, 1200m→0
            total_score += (count_score + distance_score) * weight
        total_weight += weight

    return js_round(total_score / total_weight)


def calculate_product_score(
    build_year: int | None,
    parking_ratio: float | None,
    property_fee: float | None,
    far_ratio: float | None,
    greening_rate: float | None,
) -> int | None:
    """产品力得分: 楼龄 35% + 容积率 20% + 车位比 20% + 物业费 15% + 绿化率 10%
    (子项缺失自动剔除重归一化)"""
    parts: list[dict] = []

    if build_year is not None:
        current_year = datetime.now().year
        age = max(0, current_year - build_year)
        # 当年建成 100, 每年 -2.3, 保底 30
        parts.append({"score": js_round(min(100, max(30, 100 - age * 2.3))), "weight": 35})
    if far_ratio is not None and far_ratio > 0:
        # 越低越舒适, ≤1.0 → 95-100, 每再 +1 扣 18, 保底 30
        parts.append({
            "score": js_round(max(30, min(100, 100 - max(0.0, far_ratio - 1.0) * 18))),
            "weight": 20,
        })
    if parking_ratio is not None and parking_ratio >= 0:
        # 35 + 比值×50 (0.8→75, ≥1.3 封顶 100, 0→35)
        parts.append({"score": js_round(min(100, max(30, 35 + parking_ratio * 50))), "weight": 20})
    if property_fee is not None and property_fee >= 0:
        # 45 + 月费×15 (2元→75, ≥3.3 封顶 95; 视为服务品质代理指标)
        parts.append({"score": js_round(min(95, max(40, 45 + property_fee * 15))), "weight": 15})
    if greening_rate is not None and greening_rate >= 0:
        # 30 + 百分比×1.6 (30%→78, 40%→94)
        parts.append({"score": js_round(min(100, max(30, 30 + greening_rate * 1.6))), "weight": 10})

    if len(parts) == 0:
        return None
    weight_sum = sum(p["weight"] for p in parts)
    return js_round(sum(p["score"] * p["weight"] for p in parts) / weight_sum)


def calculate_market_score(deal_count: float | None) -> int | None:
    """市场面得分: 近月签约套数 (单月快照噪声大, 权重宜低)
    0 套=30, 每套 +6.5, 封顶 95"""
    if deal_count is None:
        return None
    if deal_count <= 0:
        return 30
    return js_round(min(95, 35 + deal_count * 6.5))


# ---------------------------------------------------------------------------
# 综合评分
# ---------------------------------------------------------------------------

def calculate_score(community: dict, weights: dict | None = None) -> dict:
    """计算小区综合评分。

    权重按各维度之和归一化; 无数据的维度(得分null)剔除后重归一化, 保证各小区可比。
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    nearest_subway = community.get("nearest_subway")
    location_score = calculate_location_score(
        nearest_subway.get("distance") if nearest_subway else None
    )
    amenity_score = calculate_amenity_score(community.get("pois") or [])
    price = community.get("price") or {}
    product_score = calculate_product_score(
        community.get("build_year"),
        community.get("parking_ratio"),
        community.get("property_fee"),
        community.get("far_ratio"),
        community.get("greening_rate"),
    )
    market_score = calculate_market_score(price.get("deal_count"))

    parts: list[tuple[int, int]] = []
    if location_score is not None:
        parts.append((location_score, weights["location"]))
    if amenity_score is not None:
        parts.append((amenity_score, weights["amenity"]))
    if product_score is not None:
        parts.append((product_score, weights["product"]))
    if market_score is not None:
        parts.append((market_score, weights["market"]))

    weight_sum = sum(w for _, w in parts)
    total_score = (
        js_round(sum(s * w for s, w in parts) / weight_sum) if weight_sum > 0 else 50
    )

    return {
        "total_score": min(100, max(0, total_score)),
        "location_score": location_score,
        "product_score": product_score,
        "amenity_score": amenity_score,
        "market_score": market_score,
    }


def calculate_all_scores(communities: list[dict], weights: dict | None = None) -> list[dict]:
    """批量计算所有小区评分"""
    if weights is None:
        weights = DEFAULT_WEIGHTS
    return [{**community, "score": calculate_score(community, weights)} for community in communities]
