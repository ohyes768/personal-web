"""Rental candidate decisions live in the authoritative community registry.

Fang is retired: there is no candidate pool and no source search here. What
remains is the eligibility rules, the human review record and the skip/reopen
decisions that the matching and probe flows rely on.
"""
import hashlib
import json
import logging

from src.services.community_registry import dump, now
from src.services.residential_classifier import classify_sources
from src.services.community_address import effective_address
from src.services.community_listing import listing_gate
from src.services.tmsf_property_type import effective_market_state
from src.services.rental_reference.providers import active_sources

PREFIX = 'rental_review:'
logger = logging.getLogger(__name__)


def eligible_communities(registry):
    from src.services.directory_workflow import is_enabled, admitted
    if is_enabled(registry):
        return [c for c in admitted(registry, registry.path.parent)
                if (c.get('district') or '').removesuffix('区') == '滨江'
                and c.get('market_state') != 'new_house'], len(registry.communities())
    path = registry.path.parent / 'property_types.json'
    properties = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    sources = registry.sources()
    newhouse_ids = {r['community_id'] for r in sources
                    if r['source'] == 'tmsf' and r['status'] == 'matched'
                    and effective_market_state(r) == 'new_house'}
    communities = registry.communities()
    return [c for c in communities if c['community_id'] not in newhouse_ids
            and effective_address(c.get('address'),
            [r for r in sources if r['community_id'] == c['community_id'] and r['status'] == 'matched']) and (c.get('district') or '').removesuffix('区') == '滨江'
            and listing_gate([r for r in sources if r['community_id'] == c['community_id']
                               and r['status'] == 'matched'], c)[0] is None
            and classify_sources([r for r in sources if r['community_id'] == c['community_id']
                                  and r['status'] == 'matched'], properties) == 'residential'], len(communities)


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


def decide(registry, cid, action, candidate_id=None):
    """Skip or reopen a community's rental-source review.

    Binding happens in the Xingfuli probe flow; the retired Fang candidate
    bind is no longer available here.
    """
    communities, _ = eligible_communities(registry)
    community = next((c for c in communities if c['community_id'] == cid), None)
    if not community:
        raise ValueError('小区已删除或不是有效滨江住宅，请刷新')
    if cid in active_sources(registry):
        raise ValueError('小区已绑定租金来源，请刷新')
    if action == 'bind':
        raise ValueError('请在幸福里候选中选择对应小区主页')
    if action == 'reopen':
        with registry.db() as db:
            db.execute('DELETE FROM meta WHERE key=?', (PREFIX + cid,))
    save_review(registry, community, 'skipped' if action == 'skip' else 'missing', [])
    with registry.db() as db:
        registry._event(db, cid, 'rental_' + action, {'record_id': candidate_id})
