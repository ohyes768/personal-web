"""WGS84 与 GCJ02 互转。

与住宅面、交通转换脚本原来的实现同一套公式：国测局公开偏移，
Krasovsky 椭球。中国大陆范围外不偏移。逆变换用两次迭代逼近。
本模块不读取数据、不访问网络。
"""
from __future__ import annotations

import math

_A = 6378245.0
_EE = 0.00669342162296594323
_CHINA = (72.004, 137.8347, 0.8293, 55.8271)


def _in_china(lng: float, lat: float) -> bool:
    west, east, south, north = _CHINA
    return west <= lng <= east and south <= lat <= north


def transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    if not _in_china(lng, lat):
        return lng, lat
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lon(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng: float, lat: float, iterations: int = 2) -> tuple[float, float]:
    """迭代逼近逆变换。两次后残差远小于楼块尺度。"""
    if not _in_china(lng, lat):
        return lng, lat
    wlng, wlat = lng, lat
    for _ in range(iterations):
        glng, glat = wgs84_to_gcj02(wlng, wlat)
        wlng += lng - glng
        wlat += lat - glat
    return wlng, wlat
