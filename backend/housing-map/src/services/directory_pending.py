"""Read-only, identity-based projection of manual directory work."""
from src.services.collection_pipeline import pending_operation_bucket
from src.services.community_review import community_matches

RENTAL_REASONS = {'needs_selection', 'search_failed', 'missing', 'skipped'}
RENTAL_LABELS = {'needs_selection': '待确认租金来源', 'search_failed': '租金来源查找失败',
                 'missing': '未找到租金来源', 'skipped': '已跳过租金来源'}
PRIORITY = {'needs_selection': 0, 'search_failed': 1, 'missing': 2, 'skipped': 3}


def project(catalog, auctions, rentals):
    """Build once before filtering/paging; unresolved assets never merge by name."""
    indexed = {c['community_id']: c for c in catalog}
    rows = {}

    def community(cid, fallback):
        key = 'community:' + cid
        if key not in rows:
            c = indexed.get(cid, fallback)
            rows[key] = dict(key=key, community_id=cid, name=c.get('community_name', ''),
                             address=c.get('address', ''), district=c.get('district', ''),
                             aliases=c.get('aliases', []), sources=c.get('sources', []), issues=[])
        return rows[key]

    for c in catalog:
        if c.get('workflow_state') == 'pending':
            community(c['community_id'], c)['issues'].append(dict(
                kind='admission', reason=c.get('qualification', ''),
                label=c.get('exclusion_reason') or '小区资料待核对',
                operation=pending_operation_bucket(c), use_review=c.get('use_review') or {}))
    for r in rentals:
        if r['reason'] in RENTAL_REASONS:
            community(r['community_id'], r)['issues'].append(dict(
                kind='rental', reason=r['reason'], label=RENTAL_LABELS[r['reason']], rental=r))
    for a in auctions:
        # Even a stale old target is not a verified current association.
        key = 'auction:' + a['id']
        rows[key] = dict(key=key, community_id=None, name=a['name'], address=a.get('address', ''),
                         district=a.get('district', ''), sources=[], issues=[dict(
                             kind='auction', reason='skipped' if a.get('skipped') else 'unmatched',
                             label='已跳过法拍关联' if a.get('skipped') else a['reason'], auction=a)])
    return list(rows.values())


def query(rows, *, q='', district='', kind='', rental_status='', include_skipped=False,
          operation='', use='', use_filters=None, page=1, page_size=30):
    def active(row, include):
        return {**row, 'issues': [i for i in row['issues'] if include or i['reason'] != 'skipped']}

    defaults = [active(r, False) for r in rows]
    default_total = sum(bool(r['issues']) for r in defaults)
    base = [active(r, include_skipped) for r in rows]
    base = [r for r in base if r['issues'] and community_matches(
        {**r, 'community_name': r['name']}, r['sources'], q=q, district=district)]
    counts = {'all': len(base), **{k: sum(any(i['kind'] == k for i in r['issues']) for r in base)
                                      for k in ('admission', 'auction', 'rental')}}
    visible = []
    for row in base:
        issues = [i for i in row['issues'] if not kind or i['kind'] == kind]
        if kind == 'rental' and rental_status:
            issues = [i for i in issues if i['reason'] == rental_status]
        if kind == 'admission':
            if operation:
                issues = [i for i in issues if i['operation'] == operation]
            if use:
                issues = [i for i in issues if use_filters[use](i['use_review'])]
        if issues:
            visible.append({**row, 'issues': issues})
    visible.sort(key=lambda r: (min(PRIORITY.get(i['reason'], 0) for i in r['issues']),
                                r['name'], r['key']))
    total = len(visible)
    page = min(page, max(1, (total + page_size - 1) // page_size))
    return dict(items=visible[(page - 1) * page_size:page * page_size], total=total,
                page=page, page_size=page_size, counts=counts, default_pending_total=default_total)


def load(registry, catalog=None):
    from src.services import directory_workflow as flow
    from src.services.rental_reference.matching import source_reviews
    from src.services.rental_reference.probe import read_state
    catalog = catalog if catalog is not None else flow.inventory(registry, registry.path.parent)
    rentals = [r for r in source_reviews(registry)
               if r['reason'] != 'missing' or read_state(registry, r['community_id']).get('stage') == 'homepage_not_found']
    return project(catalog, flow.auction_tasks(registry, registry.path.parent, include_skipped=True), rentals)
