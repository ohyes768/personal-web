"""boundary 模块测试: 334 点边界 + 射线法点内判断 + 萧山接壤板块多围栏"""

from src.core.boundary import (
    BINJIANG_BOUNDARY,
    XIAOSHAN_BORDER_BOUNDARIES,
    is_in_binjiang,
    is_in_scope,
    is_in_xiaoshan_border,
)


def test_boundary_has_334_points():
    # 源 binjiang-boundary.ts 硬编码 334 点, 点数是 /api/transit meta.boundary_points 的输出
    assert len(BINJIANG_BOUNDARY) == 334


def test_boundary_polygon_closed():
    # 首尾点闭合, 射线法依赖隐式首尾相连
    assert BINJIANG_BOUNDARY[0] == BINJIANG_BOUNDARY[-1]


def test_points_inside_district():
    # 滨江区腹地采样点 (钱塘江南岸, 长河/西兴一带)
    assert is_in_binjiang(120.18, 30.18) is True
    assert is_in_binjiang(120.19, 30.19) is True
    assert is_in_binjiang(120.21, 30.21) is True


def test_points_outside_district():
    # 区外: 北京 / 滨江以东 (萧山方向) / 西南远处
    assert is_in_binjiang(116.4, 39.9) is False
    assert is_in_binjiang(120.30, 30.19) is False
    assert is_in_binjiang(120.00, 30.00) is False


def test_community_coordinates_inside():
    # 真实小区坐标 (万科璞悦湾: 浙江省杭州市滨江区) 应落在围栏内
    assert is_in_binjiang(120.137067, 30.170667) is True


# ---------------------------------------------------------------------------
# 萧山接壤板块 (盈丰/宁围/闻堰) — 2026-10 围栏扩展
# ---------------------------------------------------------------------------

def test_xiaoshan_plates_present_and_closed():
    assert set(XIAOSHAN_BORDER_BOUNDARIES) == {"闻堰", "宁围", "盈丰"}
    for name, polygon in XIAOSHAN_BORDER_BOUNDARIES.items():
        assert len(polygon) >= 30, f"{name} 围栏点数异常少: {len(polygon)}"
        assert polygon[0] == polygon[-1], f"{name} 围栏未闭合"


def test_scope_covers_binjiang_and_plates():
    # 滨江腹地
    assert is_in_scope(120.18, 30.18) is True
    # 盈丰 (钱江世纪城核心, 市民中心一带)
    assert is_in_xiaoshan_border(120.246, 30.238) is True
    # 宁围
    assert is_in_xiaoshan_border(120.28, 30.245) is True
    # 闻堰
    assert is_in_xiaoshan_border(120.19, 30.135) is True
    # 以上均计入 scope
    for lng, lat in [(120.246, 30.238), (120.28, 30.245), (120.19, 30.135)]:
        assert is_in_scope(lng, lat) is True


def test_scope_excludes_non_border_xiaoshan():
    # 萧山城区 (北干/市心路一带) 在板块外
    assert is_in_xiaoshan_border(120.265, 30.168) is False
    # 义桥 (闻堰以南) 在板块外
    assert is_in_xiaoshan_border(120.16, 30.08) is False
    assert is_in_scope(120.265, 30.168) is False
    # 杭州主城 (西湖边)
    assert is_in_scope(120.15, 30.25) is False


def test_binjiang_semantics_unchanged():
    # is_in_binjiang 保持滨江单区语义: 盈丰点不算滨江
    assert is_in_binjiang(120.246, 30.238) is False
