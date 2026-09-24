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
