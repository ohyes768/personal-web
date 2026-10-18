"""Rental candidate decisions live in the authoritative community registry."""
import hashlib
import datetime as dt
import json
import logging

from src.services.community_registry import dump, now, normalized
from src.services.residential_classifier import classify_sources
from src.services.community_address import effective_address
from src.services.community_listing import listing_gate

PREFIX = 'rental_review:'
logger = logging.getLogger(__name__)


def eligible_communities(registry):
    from src.services.directory_workflow import is_enabled, admitted
    if is_enabled(registry):
        return [c for c in admitted(registry, registry.path.parent) if (c.get('district') or '').removesuffix('区') == '滨江'], len(registry.communities())
    path = registry.path.parent / 'property_types.json'
    properties = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    sources = registry.sources()
    communities = registry.communities()
    return [c for c in communities if effective_address(c.get('address'),
            [r for r in sources if r['community_id'] == c['community_id'] and r['status'] == 'matched']) and (c.get('district') or '').removesuffix('区') == '滨江'
            and listing_gate([r for r in sources if r['community_id'] == c['community_id']
                               and r['status'] == 'matched'], c)[0] is None
            and classify_sources([r for r in sources if r['community_id'] == c['community_id']
                                  and r['status'] == 'matched'], properties) == 'residential'], len(communities)


def candidates_for(registry, community):
    from src.services.name_similarity import name_similarity
    cid = community['community_id']
    names = {normalized(n) for n in [community['community_name'], community.get('community_alias'),
                                    *community.get('aliases', [])] if n}
    with registry.db() as db:
        rejected = {r[0] for r in db.execute('SELECT rid FROM rejected WHERE cid=?', (cid,))}
    previous_ids = set(read_review(registry, cid).get('candidate_ids', []))
    result = []
    for row in registry.sources():
        if row['source'] != 'fang' or row['status'] != 'pending' or row['id'] in rejected:
            continue
        source_name = normalized(row['name'])
        if row['id'] not in previous_ids and not any(
                source_name and (source_name in name or name in source_name) for name in names):
            continue
        result.append({**{k: row.get(k) for k in ('id', 'source_id', 'name', 'address', 'district', 'evidence', 'source_url')},
                       'similarity': name_similarity(community['community_name'], row.get('name'))})
    result.sort(key=lambda r: (-r['similarity'], r['id']))
    return result


def fingerprint(candidates):
    stable = sorted((r['id'], r.get('name'), r.get('address'), r.get('district')) for r in candidates)
    return hashlib.sha256(dump(stable).encode()).hexdigest()


def read_review(registry, cid):
    with registry.db() as db:
        row = db.execute('SELECT value FROM meta WHERE key=?', (PREFIX + cid,)).fetchone()
        return json.loads(row[0]) if row else {}


def save_review(registry, community, reason, candidates, message='', *, searched=False):
    cid = community['community_id']
    signature = fingerprint(candidates)
    previous = read_review(registry, cid)
    if previous.get('decision') == 'skipped' and previous.get('fingerprint') == signature:
        reason = 'skipped'
    payload = dict(community_id=cid, community_name=community['community_name'], reason=reason,
                   message=message, candidate_ids=[r['id'] for r in candidates], fingerprint=signature,
                   decision='skipped' if reason == 'skipped' else 'pending',
                   searched_at=now() if searched else previous.get('searched_at'), updated_at=now())
    with registry.db() as db:
        if not db.execute('SELECT 1 FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (cid,)).fetchone():
            return
        db.execute('INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (PREFIX + cid, dump(payload)))


def reviews(registry):
    communities, _ = eligible_communities(registry)
    mapped = {r['community_id'] for r in registry.sources() if r['source'] == 'fang' and r['status'] == 'matched'}
    items = []
    for community in communities:
        cid = community['community_id']
        if cid in mapped:
            continue
        review = read_review(registry, cid)
        if not review:
            continue
        candidates = candidates_for(registry, community)
        if review.get('decision') == 'skipped' and review.get('fingerprint') != fingerprint(candidates):
            save_review(registry, community, 'needs_selection' if candidates else 'missing', candidates)
            review = read_review(registry, cid)
        items.append({**review, 'candidates': candidates})
    # Strongest matches first so the review list reads best-evidence-first.
    items.sort(key=lambda r: max((c.get('similarity', 0) for c in r['candidates']), default=0), reverse=True)
    return items


def decide(registry, cid, action, candidate_id=None):
    communities, _ = eligible_communities(registry)
    community = next((c for c in communities if c['community_id'] == cid), None)
    if not community:
        raise ValueError('小区已删除或不是有效滨江住宅，请刷新')
    if any(r['source'] == 'fang' and r['status'] == 'matched' and r['community_id'] == cid for r in registry.sources()):
        raise ValueError('小区已绑定租金来源，请刷新')
    candidates = candidates_for(registry, community)
    if action == 'bind':
        if candidate_id not in {r['id'] for r in candidates}:
            raise ValueError('候选已变更，请刷新后重新选择')
        # Revalidate and bind in one transaction: another management tab may
        # have deleted/rebound the record since candidates were rendered.
        with registry.db() as db:
            source = db.execute("SELECT * FROM sources WHERE id=? AND status='pending'", (candidate_id,)).fetchone()
            target = db.execute('SELECT 1 FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (cid,)).fetchone()
            already = db.execute("SELECT 1 FROM sources WHERE source='fang' AND status='matched' AND cid=?", (cid,)).fetchone()
            rejected = db.execute('SELECT 1 FROM rejected WHERE rid=? AND cid=?', (candidate_id, cid)).fetchone()
            if not source or not target or already or rejected:
                raise ValueError('来源或小区已变更，请刷新后重试')
            from src.services.directory_policy import enabled, eligibility
            if enabled(db):
                from src.services.community_admission import property_facts
                master = db.execute('SELECT * FROM communities WHERE id=?', (cid,)).fetchone()
                members = [registry._source(r) for r in db.execute("SELECT * FROM sources WHERE cid=? AND status='matched'", (cid,))]
                a = db.execute('SELECT payload FROM community_admission WHERE cid=?', (cid,)).fetchone()
                if eligibility(registry._community(master), members, property_facts(registry.path.parent), json.loads(a[0]) if a else {})['admission_state'] != 'admitted':
                    raise ValueError('小区已不符合住宅条件，请刷新')
            payload = json.loads(source['payload'])
            payload['associated_at'] = now()
            db.execute("UPDATE sources SET cid=?,status='matched',method='manual',evidence=?,payload=? WHERE id=?",
                       (cid, dump(['人工确认']), dump(payload), candidate_id))
            registry._event(db, cid, 'associate', {'record_id': candidate_id, 'method': 'manual'})
            db.execute('DELETE FROM meta WHERE key=?', (PREFIX + cid,))
    else:
        if action == 'reopen':
            with registry.db() as db:
                db.execute('DELETE FROM meta WHERE key=?', (PREFIX + cid,))
        save_review(registry, community, 'skipped' if action == 'skip' else 'needs_selection' if candidates else 'missing', candidates)
    with registry.db() as db:
        registry._event(db, cid, 'rental_' + action, {'record_id': candidate_id})


def prepare_sources(registry, cancel, progress, discover, *, delay=5, budget=5, paused_reason=None):
    communities, total = eligible_communities(registry)
    report = dict(targets=len(communities), excluded=total-len(communities), checked=0,
                  matched=0, pending=0, skipped=0, missing=0, failed=0, deferred=0)
    search_unavailable = paused_reason
    requests = 0
    logger.info('Rental source check start targets=%s search_budget=%s', len(communities), budget)
    # Continue deferred searches first instead of retrying the same first 20
    # empty communities on every run.
    communities.sort(key=lambda c: (
        not (read_review(registry, c['community_id']).get('reason') == 'search_deferred' or
             read_review(registry, c['community_id']).get('message') == '本轮来源查找额度已用完，下次更新继续'),
        c['community_id']))
    for community in communities:
        if cancel.is_set():
            from src.services.fang_rentals import RentalCrawlCancelled
            raise RentalCrawlCancelled([], None)
        cid = community['community_id']
        mapped = any(r['source'] == 'fang' and r['status'] == 'matched' and r['community_id'] == cid
                     for r in registry.sources())
        reason, message = 'matched', ''
        searched = False
        if not mapped:
            candidates = candidates_for(registry, community)
            previous = read_review(registry, cid)
            skipped = previous.get('decision') == 'skipped' and previous.get('fingerprint') == fingerprint(candidates)
            if skipped:
                reason = 'skipped'
            else:
                # Preserve explicit unlink/reject: never automatically search it back into existence.
                with registry.db() as db:
                    rejected = db.execute('SELECT 1 FROM rejected WHERE cid=?', (cid,)).fetchone()
                if rejected:
                    reason = 'needs_selection' if candidates else 'missing'
                elif not candidates:
                    checked_at = previous.get('searched_at')
                    recent_empty = (previous.get('reason') == 'missing' and checked_at and
                                    dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(checked_at) < dt.timedelta(hours=24))
                    if recent_empty:
                        reason = 'missing'
                    elif search_unavailable or requests >= budget:
                        reason = 'search_deferred'
                        message = ('房天下来源查找已暂停，本小区尚未查询，下次更新继续' if search_unavailable else
                                   '本轮来源查找额度已用完，本小区尚未查询，下次更新继续')
                    else:
                        try:
                            if cancel.wait(delay):
                                from src.services.fang_rentals import RentalCrawlCancelled
                                raise RentalCrawlCancelled([], None)
                            requests += 1
                            searched = True
                            found = discover(community)
                            if not found and requests < budget:
                                alias = next((a for a in community.get('aliases', []) if a != community['community_name']), None)
                                if alias:
                                    if cancel.wait(delay):
                                        from src.services.fang_rentals import RentalCrawlCancelled
                                        raise RentalCrawlCancelled([], None)
                                    requests += 1
                                    found = discover({**community, 'community_name': alias, 'community_alias': alias})
                            if cancel.is_set():
                                from src.services.fang_rentals import RentalCrawlCancelled
                                raise RentalCrawlCancelled([], None)
                            discovered = []
                            for item in found:
                                address = item.get('source_address') or ''
                                # The internal district is not evidence about the external source.
                                district = '滨江' if '滨江区' in address else ''
                                record = registry.ingest(dict(source='fang', source_kind='community',
                                    source_id=item['source_community_id'], name=item['source_name'],
                                    **({'address': address} if address else {}),
                                    **({'district': district} if district else {}), source_url=item['source_url']))
                                if record['status'] == 'pending':
                                    discovered.append({k: record.get(k) for k in ('id','source_id','name','address','district','evidence','source_url')})
                            candidates = list({r['id']: r for r in [*candidates_for(registry, community), *discovered]}.values())
                        except ValueError as exc:
                            from src.services.fang_request_policy import FangChallenge, FangCoolingDown
                            logger.exception('Rental source search paused community_id=%s name=%r requests=%s',
                                             cid, community['community_name'], requests)
                            if isinstance(exc, FangChallenge):
                                search_unavailable = f'{exc}，本轮暂停来源查找'
                            else:
                                search_unavailable = '房天下搜索未生效或要求验证，本轮暂停来源查找'
                            if isinstance(exc, FangCoolingDown):
                                reason, message, searched = 'search_deferred', search_unavailable, False
                                requests -= 1
                            else:
                                reason, message = 'search_failed', search_unavailable
                        except Exception as exc:
                            from src.services.fang_rentals import RentalCrawlCancelled
                            if isinstance(exc, RentalCrawlCancelled):
                                raise
                            logger.exception('Rental source search paused community_id=%s name=%r requests=%s',
                                             cid, community['community_name'], requests)
                            search_unavailable = '房天下暂时无法访问，本轮暂停来源查找'
                            reason, message = 'search_failed', search_unavailable
                for candidate in candidates:
                    registry.auto_associate(candidate['id'])
                mapped = any(r['source'] == 'fang' and r['status'] == 'matched' and r['community_id'] == cid
                             for r in registry.sources())
                if mapped:
                    reason = 'matched'
                elif reason not in {'search_failed', 'search_deferred'}:
                    reason = 'needs_selection' if candidates else 'missing'
            if not mapped:
                save_review(registry, community, reason, candidates, message, searched=searched)
            report[{'matched':'matched', 'needs_selection':'pending', 'skipped':'skipped',
                    'missing':'missing', 'search_failed':'failed', 'search_deferred':'deferred'}[reason]] += 1
        else:
            report['matched'] += 1
        report['checked'] += 1
        progress(dict(report))
    effective = {c['community_id'] for c in eligible_communities(registry)[0]}
    logger.info('Rental source check complete checked=%s matched=%s pending=%s missing=%s '
                'failed=%s requests=%s deferred=%s pause_reason=%r',
                report['checked'], report['matched'], report['pending'], report['missing'],
                report['failed'], requests, report['deferred'], search_unavailable)
    return [(r['source_id'], r['community_id']) for r in registry.sources()
            if r['source']=='fang' and r['status']=='matched' and r['community_id'] in effective], report
