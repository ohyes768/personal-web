"""boundary 模块测试: 334 点边界 + 射线法点内判断"""

from src.core.boundary import BINJIANG_BOUNDARY, is_in_binjiang


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
