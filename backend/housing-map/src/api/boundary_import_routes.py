"""小区轮廓导入接口:单 token 门禁 + 逐条校验 + 幂等落盘。

线上经 nginx 公网可达,故此接口是本服务唯一带鉴权的写入口:
未配置 HOUSING_ADMIN_TOKEN 时整体禁用(503),token 不匹配 401。
"""
import hmac
import math
import os
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.core.boundary import is_in_scope
from src.services.boundary_import import merge_boundaries
from src.services.data_loader import load_display_communities

router = APIRouter(tags=["map"])


class BoundaryItem(BaseModel):
    community_id: str
    coordinate_system: Literal["gcj02"]
    rings: list[list[list[float]]]
    meta: dict | None = None


class BoundaryImportRequest(BaseModel):
    source: Literal["osm-building"]
    boundaries: list[BoundaryItem]


def _admin_token() -> str | None:
    return os.getenv("HOUSING_ADMIN_TOKEN") or None


def _ring_sample(rings: list[list[list[float]]]) -> list[list[float]]:
    # 简化后每环点数有限,全点校验,边缘压线即拒(数据问题应回脚本重算而非静默放宽)
    return [point for ring in rings for point in ring]


def _approx_area_km2(rings: list[list[list[float]]]) -> float:
    ring = max(rings, key=len)
    lat0 = sum(point[1] for point in ring) / len(ring)
    km_lat = 110.574
    km_lng = 111.320 * math.cos(math.radians(lat0))
    pts = [(point[0] * km_lng, point[1] * km_lat) for point in ring]
    doubled = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        doubled += x1 * y2 - x2 * y1
    return abs(doubled) / 2


def _validate(item: BoundaryItem, known_ids: set[str]) -> str | None:
    if item.community_id not in known_ids:
        return "community_id 不在当前展示小区集合"
    if not item.rings:
        return "rings 为空"
    for ring in item.rings:
        if len(ring) < 4 or ring[0] != ring[-1]:
            return "ring 至少 3 个不重复点且首尾闭合"
    for lng, lat in _ring_sample(item.rings):
        if not is_in_scope(lng, lat):
            return "坐标超出滨江/萧山接壤围栏"
    if _approx_area_km2(item.rings) > 1.0:
        return "轮廓面积超过 1 平方公里(疑似粘连邻区)"
    return None


@router.post("/boundaries/import")
async def import_boundaries(payload: BoundaryImportRequest, x_admin_token: str | None = Header(default=None)):
    expected = _admin_token()
    if not expected:
        raise HTTPException(status_code=503, detail="轮廓上传未启用:未配置 HOUSING_ADMIN_TOKEN")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="invalid admin token")

    known_ids = {c["community_id"] for c in load_display_communities()}
    accepted, rejected = [], []
    for item in payload.boundaries:
        reason = _validate(item, known_ids)
        if reason:
            rejected.append({"community_id": item.community_id, "reason": reason})
        else:
            accepted.append({
                "community_id": item.community_id,
                "source": payload.source,
                "rings": item.rings,
                "meta": item.meta,
            })
    if accepted:
        merge_boundaries(accepted)
    return {"success": True, "data": {
        "accepted": [item["community_id"] for item in accepted],
        "rejected": rejected,
    }}
