"""Choose one confirmed rental provider per community without mixing snapshots."""

# 唯一当前租金来源。房天下已退役，历史关联仍可读取，但不再参与当前采集与统计。
CURRENT_RENTAL_PROVIDER = 'xingfuli'


def rejected_rental_communities(db):
    """Keep unrelated source unlinks out of rental-source vetoes."""
    return {row[0] for row in db.execute(
        "SELECT DISTINCT r.cid FROM rejected r JOIN sources s ON s.id=r.rid "
        "WHERE s.source IN ('fang','xingfuli')")}


def active_sources(registry):
    """当前可采集的租金来源：只认幸福里且社区必须有效。

    历史房天下关联保留在台账里但不参与当前采集，因此不会与幸福里竞争同一个小区。
    """
    selected = {}
    for row in registry.sources():
        if row['source'] != CURRENT_RENTAL_PROVIDER:
            continue
        if (row['status'] != 'matched'
                or not row.get('community_id') or not registry.resolve(row['community_id'])):
            continue
        cid = row['community_id']
        previous = selected.get(cid)
        if previous and previous['source'] == row['source']:
            raise ValueError('同一小区有多个有效租金来源，请先核对关联')
        selected[cid] = row
    return selected


def same_source(entry, source, sid):
    """来源身份必须显式匹配；缺 provider 的旧快照不得当作幸福里复用。"""
    if source != CURRENT_RENTAL_PROVIDER:
        return False
    return bool(entry and entry.get('source') == CURRENT_RENTAL_PROVIDER
                and entry.get('source_community_id') == sid)


def source_url(record):
    if record.get('source') == CURRENT_RENTAL_PROVIDER:
        from src.services.xingfuli_rentals import list_url
        return list_url(record.get('seed_listing_id'))
    raise ValueError(f"unsupported rental source: {record.get('source')!r}")
