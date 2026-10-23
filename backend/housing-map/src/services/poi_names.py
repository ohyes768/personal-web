"""POI 与小区名称匹配规则。

定位关联与用途复核共用同一套拉平/别名/包含规则，避免两处实现各自漂移。
"""
import re

from src.services.community_registry import normalized

_DOT = str.maketrans('', '', '·・･')
_GENERIC_SUFFIX = ('小区', '花园', '公寓', '大厦', '公馆', '邸', '苑', '院', '府')


def flat_name(value):
    """拉平名称：去掉括号说明、中点与通用小区后缀。中海·钱塘山水 → 中海钱塘山水。"""
    stem = re.sub(r'[（(][^（）()]*[)）]', '', str(value or ''))
    stem = normalized(stem).translate(_DOT)
    changed = True
    while changed:
        changed = False
        for suffix in _GENERIC_SUFFIX:
            if stem.endswith(suffix) and len(stem) > len(suffix):
                stem = stem[:-len(suffix)]
                changed = True
    return stem


def name_hit(poi_name, flats):
    """名称相等或互相包含即命中；较短一侧长度需 >= 3。"""
    name = flat_name(poi_name)
    if not name:
        return False
    return name in flats or any((len(n) >= 3 and n in name) or (len(name) >= 3 and name in n) for n in flats if n)


def match_kind(poi_name, names):
    """命中方式：exact（与主名一致）/ alias（与别名一致）/ loose（仅包含命中）。"""
    flat = flat_name(poi_name)
    if not flat:
        return None
    loose = None
    for index, value in enumerate(names):
        candidate = flat_name(value) if value else ''
        if not candidate:
            continue
        if flat == candidate:
            return 'exact' if index == 0 else 'alias'
        if (len(candidate) >= 3 and candidate in flat) or (len(flat) >= 3 and flat in candidate):
            loose = loose or 'loose'
    return loose
