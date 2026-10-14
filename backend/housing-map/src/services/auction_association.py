"""Bridge saved auction rounds to durable directory decisions, without upstream calls."""
from collections import defaultdict
import sqlite3

from src.services.auction_store import read_store
from src.services.community_directory import prepare_directory
from src.services.community_registry import existing_registry


def identity(row):
    asset = str(row.get('asset_id') or '').strip()
    return row['source'], 'asset' if asset else 'auction', asset or str(row['auction_id'])


def groups(rows):
    grouped = defaultdict(list)
    for row in rows:
        if row.get('source') == 'laipai':
            grouped[identity(row)].append(row)
    return grouped


def sync_records(path):
    rows = read_store(path)['records']
    store = prepare_directory(path.parent)
    report = dict(records=len(rows), identities=0, matched=0, automatic=0, pending=0, ignored=0)
    for (source, kind, sid), rounds in groups(rows).items():
        report['identities'] += 1
        # An ignored round is also authoritative when an asset identity appears later.
        if store.is_ignored(source, kind, sid) or any(
                store.is_ignored(source, 'auction', r['auction_id']) for r in rounds):
            report['ignored'] += 1
            continue
        decisions_consistent = kind != 'asset' or store.promote_auction_source(sid, [str(r['auction_id']) for r in rounds])
        latest = max(rounds, key=lambda r: (r.get('captured_at') or '', str(r['auction_id'])))
        named = [r for r in rounds if (r.get('community_name') or '').strip()]
        name_row = max(named, key=lambda r: (r.get('captured_at') or '', str(r['auction_id']))) if named else latest
        item = store.ingest(dict(source=source, source_kind=kind, source_id=sid,
            name=name_row.get('community_name') or latest.get('title') or '小区名称缺失',
            community_name_missing=not bool(named), auction_title=latest.get('title'),
            auto_association_disabled=not bool(named) or not decisions_consistent,
            association_identity_conflict=not decisions_consistent, district='滨江',
            address=latest.get('address') or '', source_url=latest.get('source_url'),
            auction_ids=list(dict.fromkeys(str(r['auction_id']) for r in rounds))))
        report[item['status'] if item['status'] in ('matched', 'ignored') else 'pending'] += 1
        if item['status'] == 'matched' and item['method'] == 'auto':
            report['automatic'] += 1
    from src.services.community_review import ReviewWorkspace
    ReviewWorkspace(store, path.parent).refresh()
    from src.services.community_auto_review import AutoReview
    try:
        report['auto_review'] = AutoReview(store, path.parent).after_collection()
    except (ValueError, OSError, sqlite3.Error):
        report['auto_review_error'] = '资料和审核队列已保存，自动审核未完成，请重新预演'
    return report


def pending_records(path):
    rows = read_store(path)['records']
    grouped = groups(rows)
    store = existing_registry(path.parent)
    if not store:
        return [], bool(grouped)
    sources = {(r['source'], r['source_kind'], r['source_id']): r for r in store.sources()}
    pending, needs_sync = [], False
    for key, rounds in grouped.items():
        source, kind, sid = key
        if store.is_ignored(source, kind, sid) or any(
                store.is_ignored(source, 'auction', r['auction_id']) for r in rounds):
            continue
        item = sources.get(key)
        if not item:
            needs_sync = True
            continue
        if any(str(r['auction_id']) not in item.get('auction_ids', []) for r in rounds):
            needs_sync = True
        if item['status'] != 'pending':
            continue
        candidates = store.candidates(item)
        if item.get('association_identity_conflict'):
            reason = '旧拍卖轮次存在独立关联决定，请人工核对房产归属'
        elif item.get('auto_association_disabled'):
            reason = '来源未提供小区名称，请根据地址核对'
        elif not candidates:
            reason = '没有可用名称候选，或候选已被人工排除'
        elif len(candidates) > 1:
            reason = '存在多个候选，请核对名称、地址和分期'
        else:
            reason = '证据不足或已有人工决定，请核对后确认'
        pending.append(dict(record_id=item['id'], name=item['name'], address=item.get('address'),
            source_kind=kind, source_id=sid, reason=reason, candidates=candidates,
            rounds=[{k: r.get(k) for k in ('auction_id', 'title', 'status', 'round', 'source_url')}
                    for r in rounds]))
    return sorted(pending, key=lambda r: (r['name'], r['source_id'])), needs_sync
