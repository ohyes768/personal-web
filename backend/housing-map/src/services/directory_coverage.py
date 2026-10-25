"""Read-only data coverage for the management catalog, independent of admission."""
import datetime as dt
import json
from collections import defaultdict

from src.services.auction_history import property_key
from src.services.auction_store import read_store
from src.services.rental_reference.statistics import is_stale, parse_utc, select_valid
from src.services.rental_reference.storage import load_current
from src.services.rental_reference.providers import active_sources


def attach_coverage(rows, registry, data_dir, *, include_records=False):
    """Batch read business data once; never discover sources or rewrite decisions."""
    sources = registry.sources()
    with registry.db() as db:
        reviews = {r['key'].removeprefix('rental_review:'): json.loads(r['value'])
                   for r in db.execute("SELECT key,value FROM meta WHERE key LIKE 'rental_review:%'")}
    auctions = auction_records(sources, read_store(data_dir / 'auction_records.json')['records'])
    current = load_current(data_dir / 'rentals')
    entries = {(e.get('source', 'fang'), e.get('source_community_id')): e
               for e in (current or {}).get('communities', {}).values()}
    mappings = active_sources(registry)
    job_path = data_dir / 'rentals' / 'refresh_job.json'
    job = json.loads(job_path.read_text(encoding='utf-8')) if job_path.exists() else {}
    clock = dt.datetime.now(dt.UTC)
    output = []
    for row in rows:
        cid = row['community_id']
        records = auctions.get(cid, [])
        identified = {property_key(r) for r in records if r.get('asset_id')}
        unknown = {property_key(r) for r in records if not r.get('asset_id')}
        rental = rental_coverage(mappings.get(cid), entries, reviews.get(cid, {}), job, now=clock)
        value = {**row, 'coverage': {
            'auction': dict(property_count=len(identified), round_count=len(records), unidentified_round_count=len(unknown)),
            'rental': rental}}
        if include_records:
            # Whitelist public property facts; do not return upstream announcements.
            value['auction_records'] = [{k: r.get(k) for k in (
                'source', 'auction_id', 'asset_id', 'title', 'round', 'status', 'source_url', 'end_at')}
                for r in records]
        output.append(value)
    return output


def auction_records(sources, records):
    decisions = {(s['source'], s['source_kind'], s['source_id']): s for s in sources if s['source'] == 'laipai'}
    result = defaultdict(list)
    seen = set()
    for row in records:
        identities = [(row['source'], 'asset', str(row.get('asset_id') or '')),
                      (row['source'], 'auction', str(row['auction_id']))]
        matches = [decisions[key] for key in identities if key in decisions]
        if any(s['status'] == 'ignored' for s in matches):
            continue
        # An existing asset decision takes precedence over an old round decision,
        # including an asset that is now pending or explicitly unlinked.
        decision = matches[0] if matches else None
        key = row['source'], str(row['auction_id'])
        if decision and decision['status'] == 'matched' and decision['community_id'] and key not in seen:
            result[decision['community_id']].append(row)
            seen.add(key)
    return result


def rental_coverage(mapping, entries, review, job, *, now):
    entry = entries.get((mapping['source'], mapping['source_id'])) if mapping else None
    valid = select_valid(entry.get('samples') or [])[0] if entry else []
    error = None
    if mapping:
        associated = parse_utc(mapping.get('associated_at'))
        started = parse_utc(job.get('started_at'))
        if associated and started and started >= associated:
            error = next((e.get('error') or e.get('message') for e in (job.get('errors') or {}).get('items', [])
                          if e.get('community_id') == mapping['community_id'] and (e.get('error') or e.get('message'))), None)
    if valid:
        state = 'data'
    elif error:
        state = 'failed'
    elif entry:
        state = 'no_samples'
    elif mapping:
        state = 'pending'
    else:
        state = {'needs_selection': 'unmapped', 'skipped': 'unmapped', 'missing': 'source_missing',
                 'search_failed': 'failed'}.get(review.get('reason'), 'pending')
        if state == 'failed':
            error = review.get('message') or '租金来源查询失败'
    return dict(state=state, sample_count=len(valid), captured_at=entry.get('captured_at') if entry else None,
                stale=is_stale(entry.get('captured_at'), now=now) if entry else False,
                update_failed=bool(error), error=error)
