"""Choose one confirmed rental provider per community without mixing snapshots."""

RENTAL_PROVIDERS = frozenset({'fang', 'xingfuli'})


def active_sources(registry):
    selected = {}
    for row in registry.sources():
        if (row['source'] not in RENTAL_PROVIDERS or row['status'] != 'matched'
                or not row.get('community_id') or not registry.resolve(row['community_id'])):
            continue
        cid = row['community_id']
        previous = selected.get(cid)
        if previous and previous['source'] == row['source']:
            raise ValueError('同一小区有多个有效租金来源，请先核对关联')
        if not previous or row['source'] == 'xingfuli':
            selected[cid] = row
    return selected


def same_source(entry, source, sid):
    return bool(entry and entry.get('source', 'fang') == source and entry.get('source_community_id') == sid)


def source_url(record):
    if record['source'] == 'xingfuli':
        from src.services.xingfuli_rentals import list_url
        return list_url(record.get('seed_listing_id'))
    return f"https://zu.fang.com/hz/house-xm{record['source_id']}/"
