"""高德用途分类复核：分类映射、证据选择与 TMSF↔高德 决策矩阵。

高德分类只是第二来源证据：它可以制造待审核冲突、支撑人工确认，
但永不自动收录或排除。本模块是纯函数层，不触碰数据库与网络。
"""
import hashlib

from src.services.amap_directory import normalize_poi_category
from src.services.community_registry import dump
from src.services.name_similarity import name_similarity
from src.services.poi_names import flat_name, match_kind, name_hit
from src.services.residential_classifier import NON_RESIDENTIAL_TYPES, RESIDENTIAL_TYPES

RULE_VERSION = 'use-review-v1'

# 用途分类
RESIDENTIAL = 'residential'
MIXED = 'mixed'
NON_RESIDENTIAL = 'non_residential'
UNKNOWN = 'unknown'

# 高德住宅类分类码：住宅类/住宅区/住宅小区/别墅区/别墅
RESIDENTIAL_TYPECODES = frozenset({'120300', '120301', '120302', '120303', '120304'})
# 商住两用楼宇：TMSF 住宅项目常落在该分类下，用途性质待确认。
MIXED_TYPECODES = frozenset({'120203'})

# 复核证据状态
CHECKED = 'checked'
NOT_FOUND = 'not_found'
ERROR = 'error'
UNCERTAIN = 'uncertain'

# 决策矩阵结果
AGREE_RESIDENTIAL = 'agree_residential'
AGREE_NON_RESIDENTIAL = 'agree_non_residential'
CONFLICT = 'conflict'
UNCERTAIN_RESULT = 'uncertain'
PENDING_RETRY = 'pending_retry'


def amap_category(typecode):
    """高德分类码 → 用途分类。复合码按 `|` 分段，任一段命中住宅码即住宅。"""
    parts = {part for part in str(typecode or '').split('|') if part}
    if not parts:
        return None
    if parts & RESIDENTIAL_TYPECODES:
        return RESIDENTIAL
    if parts & MIXED_TYPECODES:
        return MIXED
    return NON_RESIDENTIAL


def tmsf_category(types):
    """透明售房网用途集合 → 住宅 / 非住宅 / 不明。"""
    values = {value for value in (types or []) if value}
    if not values:
        return None
    if values <= RESIDENTIAL_TYPES:
        return RESIDENTIAL
    if values <= NON_RESIDENTIAL_TYPES:
        return NON_RESIDENTIAL
    return UNKNOWN


def compare(types, amap):
    """透明售房网用途与高德分类的决策矩阵结果。

    `amap` 为 None 表示没有可用证据（未找到/查询失败/匹配不确定），
    此时返回 pending_retry，透明售房网的原判定保持不变。
    """
    if amap is None:
        return PENDING_RETRY
    source = tmsf_category(types)
    if amap == MIXED or source in (None, UNKNOWN):
        return UNCERTAIN_RESULT
    if source == amap:
        return AGREE_RESIDENTIAL if source == RESIDENTIAL else AGREE_NON_RESIDENTIAL
    return CONFLICT


def select_evidence(pois, community):
    """从不限类型的高德 POI 中挑出同区名称匹配证据。

    0 个名称匹配 → not_found；多个候选分类不一致 → uncertain；
    分类一致 → 采用该分类并记录代表 POI。
    """
    district = (community.get('district') or '').removesuffix('区')
    names = [community.get('community_name'), community.get('community_alias'), *community.get('aliases', [])]
    flats = {flat_name(name) for name in names if name}
    matched = []
    for raw in pois or []:
        poi = normalize_poi_category(raw, district=district)
        if not poi or not name_hit(poi['name'], flats):
            continue
        matched.append({**poi, 'matched_by': match_kind(poi['name'], names) or 'loose'})
    if not matched:
        return dict(state=NOT_FOUND, category=None, evidence=None, candidates_count=0)
    categories = {amap_category(poi['poi_typecode']) for poi in matched}
    if len(categories) != 1 or None in categories:
        return dict(state=UNCERTAIN, category=None, evidence=None, candidates_count=len(matched))
    representative = max(matched, key=lambda poi: max(
        (name_similarity(name, poi['name']) for name in names if name), default=0.0))
    return dict(state=CHECKED, category=categories.pop(), evidence=_evidence(representative),
                candidates_count=len(matched))


def _evidence(poi):
    return dict(poi_id=poi['source_id'], name=poi['name'], typecode=poi['poi_typecode'],
                type_text=poi.get('poi_type') or '', address=poi.get('address') or '',
                longitude=poi.get('longitude'), latitude=poi.get('latitude'),
                district=poi.get('district'), matched_by=poi.get('matched_by'))


def use_identity(target):
    """复核证据的身份指纹。

    小区身份（名称/别名/区域）变化才让旧证据失效。实际地址不参与：
    地址在采集后补全或纠正，与用途分类无关，却会让已确认的分类冲突
    静默退回透明售房网的原判定。
    """
    return hashlib.sha256(dump({k: target.get(k) for k in
        ('community_id', 'community_name', 'aliases', 'district')}).encode()).hexdigest()


def use_review_view(target):
    """复核证据投影。身份指纹或规则版本变化即视为无证据。"""
    from src.services.collection_pipeline import active, selected_review
    if active(target):
        return selected_review(target)
    saved = target.get('use_review') or {}
    if not saved or saved.get('identity') != use_identity(target) or saved.get('rule_version') != RULE_VERSION:
        return dict(state=None, category=None, checked_at=None, error=None, evidence=None, candidates_count=0)
    return dict(state=saved.get('state'), category=saved.get('category'),
                checked_at=saved.get('checked_at'), error=saved.get('error'),
                evidence=saved.get('evidence'), candidates_count=saved.get('candidates_count') or 0)


def use_review_projection(community, records=(), admission=None, facts=None):
    """目录行的高德用途复核投影：证据、矩阵结论与人工决定。"""
    admission = admission if admission is not None else (community.get('admission') or {})
    from src.services.collection_pipeline import active, selected_review
    review = selected_review(community, records) if active(community) else use_review_view(community)
    records = [record for record in records or [] if record.get('source') == 'tmsf']
    types = {value for value in tmsf_property_types(records, facts) if value}
    category = review.get('category') if review.get('state') == CHECKED else None
    human = None
    re_review = False
    if admission.get('use_rule') == RULE_VERSION and admission.get('use_decision'):
        human = dict(decision=admission['use_decision'], decided_at=admission.get('decided_at'),
                     reason=admission.get('reason') or '', evidence=admission.get('use_evidence') or [])
        re_review = bool(contrary_evidence(admission, records, review))
    return dict(state=review.get('state'), category=review.get('category'),
                result=compare(types, category), checked_at=review.get('checked_at'),
                error=review.get('error'), evidence=review.get('evidence'),
                candidates_count=review.get('candidates_count') or 0,
                human=human, re_review=re_review)


def tmsf_property_types(records, facts=None):
    """每个透明售房网记录的用途（缺失返回 None），与资格判定同口径。"""
    values = []
    for record in records or []:
        prop = record.get('property_type')
        if not prop and not record.get('property_type_checked_at') and record.get('source_kind') != 'project':
            prop = (facts or {}).get(str(record['source_id']), {}).get('property_type')
        values.append(prop or None)
    return values


def contrary_evidence(admission, records, review):
    """人工用途决定之后出现的相反证据；没有则返回 None。

    高德复核结论与人工决定相反，或透明售房网在决定之后更新了用途证据，
    都让用途重新回到待人工审核。已存决定不删除、不覆盖。
    """
    decision = admission.get('use_decision')
    decided_at = admission.get('decided_at') or ''
    if decision not in {'residential', 'non_residential'} or not decided_at:
        return None
    if review.get('state') == CHECKED and (review.get('checked_at') or '') > decided_at:
        category = review.get('category')
        if decision == 'residential' and category in {NON_RESIDENTIAL, MIXED}:
            return f'高德复核为{_category_text(category)}，与人工确认的住宅用途相反'
        if decision == 'non_residential' and category == RESIDENTIAL:
            return '高德复核为住宅小区，与人工确认的非住宅用途相反'
    for record in records or []:
        if (record.get('property_type_checked_at') or '') <= decided_at:
            continue
        if record.get('property_type_conflict'):
            return '透明售房网用途证据出现冲突'
        prop = record.get('property_type')
        if decision == 'residential' and prop and prop not in RESIDENTIAL_TYPES:
            return f'透明售房网更新为{prop}，与人工确认的住宅用途相反'
        if decision == 'non_residential' and prop in RESIDENTIAL_TYPES:
            return f'透明售房网更新为{prop}，与人工确认的非住宅用途相反'
    return None


def _category_text(category):
    return {RESIDENTIAL: '住宅小区', MIXED: '商住两用楼宇', NON_RESIDENTIAL: '非住宅'}.get(category, category)
