"""滨江购房地图的小区准入规则。

目录源会混入道路、村落和商业项目；地图和刷新任务必须复用同一规则，
避免地图不展示但仍消耗采集额度的情况。
"""

import re
from typing import Any


ROAD_NAME_SUFFIX = re.compile(r"(?:大道|路|街|巷)$")
EXCLUDED_COMMUNITY_NAMES = {"新街镇北塘河"}
RESIDENTIAL_PROPERTY_TYPES = frozenset({"住宅", "别墅", "排屋"})


def is_residential_community(community: dict[str, Any], property_types: dict[str, dict]) -> bool:
    """仅保留已核验为住宅的真实小区。"""
    name = str(community.get("community_name") or "").strip()
    community_id = str(community.get("community_id") or "")
    if not name or ROAD_NAME_SUFFIX.search(name) or name in EXCLUDED_COMMUNITY_NAMES:
        return False
    property_type = (property_types.get(community_id) or {}).get("property_type")
    return property_type in RESIDENTIAL_PROPERTY_TYPES
