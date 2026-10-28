"""滨江购房地图的小区准入规则。

目录源会混入道路、村落条目；地图下发与刷新采集用 is_real_community 排除这些垃圾条目，
其余小区（含商办类）全量抓取，展示差异交给前端物业类型筛选。
轮廓生成仍按住宅口径，用 is_residential_community。
"""

import re
from typing import Any


ROAD_NAME_SUFFIX = re.compile(r"(?:大道|路|街|巷)$")
EXCLUDED_COMMUNITY_NAMES = {"新街镇北塘河"}
RESIDENTIAL_PROPERTY_TYPES = frozenset({"住宅", "别墅", "排屋"})

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


def is_real_community(community: dict[str, Any]) -> bool:
    """排除道路名等非小区条目；物业类型不作为准入条件。"""
    name = str(community.get("community_name") or "").strip()
    if not name or ROAD_NAME_SUFFIX.search(name) or name in EXCLUDED_COMMUNITY_NAMES:
        return False
    return True


def is_residential_community(community: dict[str, Any], property_types: dict[str, dict]) -> bool:
    """仅保留已核验为住宅的真实小区（用于轮廓生成）。"""
    if not is_real_community(community):
        return False
    community_id = str(community.get("community_id") or "")
    property_type = (property_types.get(community_id) or {}).get("property_type")
    return property_type in RESIDENTIAL_PROPERTY_TYPES
