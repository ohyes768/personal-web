"""Versioned candidate-to-admission rules; no network or storage mutation on reads."""
import re

RULE = 'collection-pipeline-v2'
KEY = 'collection_pipeline_version'


def enabled(db):
    row = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
    return bool(row and row[0] == RULE)


def active(target):
    return target.get(KEY) == RULE


def selected_review(target, records=()):
    from src.services.directory_position_state import position_view
    from src.services.use_review_policy import amap_category
    view = position_view(target, records)
    point = view.get('selected') or {}
    category = amap_category(point.get('poi_typecode'))
    usable = view.get('state') in {'matched', 'manual'} and point.get('source_id') and category
    return dict(state='checked' if usable else None, category=category if usable else None,
                checked_at=view.get('confirmed_at') or view.get('checked_at'), error=None,
                candidates_count=1 if usable else 0,
                evidence=dict(poi_id=point.get('source_id'), name=point.get('name'),
                    typecode=point.get('poi_typecode'), type_text=point.get('poi_type') or '',
                    address=point.get('address'), longitude=point.get('longitude'),
                    latitude=point.get('latitude'), district=point.get('district')) if usable else None)


def position_gate(target, records, *, human_use=False):
    from src.services.directory_position_state import position_view
    from src.services.community_enrichment import valid_position
    view = position_view(target, records)
    if view.get('state') not in {'matched', 'manual'}:
        return 'position_review' if view.get('state') == 'review' else 'position_pending', '请先匹配并确认楼盘的高德主体地点'
    point = view.get('selected') or {}
    district = (target.get('district') or '').removesuffix('区')
    if not valid_position({**point, 'coordinate_system': 'gcj02'}, district):
        return 'position_pending', '已确认地点缺少有效区域内坐标，请重新匹配'
    if not selected_review(target, records)['state'] and not (human_use and view.get('state') == 'manual'):
        return 'position_type_missing', '已确认位置缺少高德主体类型，请补充证据或人工确认用途'
    return None


def subject_name(value):
    # Preserve phase and parenthetical property names; only punctuation/space normalization.
    from src.services.community_registry import normalized
    value = normalized(value)
    return re.sub(r'[\s·・･]', '', value)


def auto_subject_reliable(target, point, records=()):
    from src.services.community_address import effective_address
    names = {subject_name(n) for n in [target.get('community_name'), target.get('community_alias'),
                                      *target.get('aliases', [])] if n}
    address = subject_name(effective_address(target.get('address'), records))
    poi_address = subject_name(point.get('address'))
    def numbered(value):
        value = re.sub(r'^.*(?:省|市|区|街道)', '', value)
        hit = re.search(r'([^\d,，;；()]+(?:路|街|道|巷|弄))(\d+)号', value)
        return hit.groups() if hit else None
    # Intersection descriptions and doorplate addresses can describe the same
    # estate. Different text alone is not evidence of a different location.
    left, right = numbered(address), numbered(poi_address)
    conflict = left is not None and right is not None and left != right
    return subject_name(point.get('name')) in names and bool(poi_address) and not conflict


def subject_pois(rows, district):
    from src.services.amap_directory import normalize_poi_category
    from src.services.community_enrichment import valid_position
    valid = {}
    for raw in rows:
        p = normalize_poi_category(raw, district=district)
        if not p or not valid_position(p, district):
            continue
        # Building/estate/industrial park subjects; a shop's type cannot classify an estate.
        if not any(code.startswith('120') for code in p['poi_typecode'].split('|')):
            continue
        valid[p['source_id']] = p
    return valid


class RequestBudgetClient:
    """Lazy HTTP page budget shared across candidates, aliases and communities."""
    def __init__(self, factory, *, limit, delay, cancel):
        self.factory, self.limit, self.delay, self.cancel = factory, limit, delay, cancel
        self.client, self.used = None, 0

    def search_name(self, *args, **kwargs):
        if self.cancel.is_set():
            raise InterruptedError()
        if self.used >= self.limit:
            raise ValueError('达到本轮高德实际请求预算，未完成目标可下次重试')
        if self.used and self.cancel.wait(self.delay):
            raise InterruptedError()
        if self.client is None:
            self.client = self.factory()
        self.used += 1
        return self.client.search_name(*args, **kwargs)

    def close(self):
        if self.client:
            self.client.close()
