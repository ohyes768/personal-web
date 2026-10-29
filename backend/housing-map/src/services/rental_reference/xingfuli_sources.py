"""Turn a discovered Xingfuli community into a rental source.

Two rules decide everything here. An automatic binding needs the platform name
to match the internal community exactly and the place to agree by address or
position; a human may confirm a merely similar name, but never a phase variant
or a different district. A keyword search response is never evidence.
"""
from __future__ import annotations

import json
import logging
import math

from src.services.community_registry import dump, normalized, now
from src.services.xingfuli_discovery import address_district, phase_of
from src.services.xingfuli_rentals import list_url

logger = logging.getLogger(__name__)
POSITION_LIMIT_METERS = 100
AUTO_SEARCH_BUDGET = 5


def community_names(community):
    return [n for n in [community.get('community_name'), community.get('community_alias'),
                        *(community.get('aliases') or [])] if n]


def _distance_meters(a_lng, a_lat, b_lng, b_lat):
    dx = (a_lng - b_lng) * math.cos(math.radians(a_lat)) * 111320
    dy = (a_lat - b_lat) * 111320
    return math.hypot(dx, dy)


def _matches_name(names, platform_name):
    """How the platform name relates to the internal names."""
    platform = normalized(platform_name)
    if not platform:
        return 'none'
    for name in names:
        if normalized(name) == platform:
            return 'exact'
    if phase_of(platform_name):
        # A qualified platform name is a phase of the base community.
        return 'none'
    for name in names:
        internal = normalized(name)
        if internal and (internal in platform or platform in internal):
            return 'partial'
    return 'none'


def evaluate(community, candidate):
    """Evidence, gaps and conflicts between an internal community and a candidate."""
    names = community_names(community)
    evidence = []
    gaps = []
    conflicts = []

    match = _matches_name(names, candidate.get('name'))
    if match == 'exact':
        evidence.append('完整名称一致')
    elif match == 'partial':
        evidence.append('名称高度相似')
        gaps.append('平台名称与目录名称不完全一致')
    else:
        gaps.append('名称不匹配')

    qualifier = phase_of(candidate.get('name'))
    if qualifier and not any(qualifier in str(name or '') for name in names):
        conflicts.append(f'平台名称带分期标记“{qualifier}”，与目录小区不是同一范围')

    internal_district = (community.get('district') or '').removesuffix('区')
    candidate_district = address_district(candidate.get('address'))
    if candidate_district and candidate_district.removesuffix('区') != internal_district:
        conflicts.append(f'平台地址位于{candidate_district}，与目录区域{internal_district}不一致')

    same_address = bool(normalized(candidate.get('address'))) and \
        normalized(candidate.get('address')) == normalized(community.get('address'))
    same_position = False
    values = [candidate.get('longitude'), candidate.get('latitude'),
              community.get('longitude'), community.get('latitude')]
    if candidate.get('coordinate_system') == community.get('coordinate_system') == 'gcj02' \
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        same_position = _distance_meters(*values) <= POSITION_LIMIT_METERS
    if same_address:
        evidence.append('地址一致')
    elif same_position:
        evidence.append('位置接近（100米内）')
    else:
        gaps.append('缺少一致地址或位置证据')

    strong = match == 'exact' and not conflicts and (same_address or same_position)
    return {'evidence': evidence, 'gaps': gaps, 'conflicts': conflicts, 'strong': strong}


def candidate_from_homepage(homepage, *, discovered_via):
    """Public facts of a community homepage, ready to be shown or judged."""
    return {
        'neighborhood_id': homepage['neighborhood_id'],
        'name': homepage['name'],
        'address': homepage['address'],
        'longitude': homepage['longitude'],
        'latitude': homepage['latitude'],
        'coordinate_system': homepage['coordinate_system'],
        'phase': phase_of(homepage['name']),
        'rent_total': homepage.get('rent_total'),
        'seeds': list(homepage.get('seeds') or []),
        'discovered_via': discovered_via,
        'homepage_url': f'https://m.xflapp.com/xiaoqu/hz-{homepage["neighborhood_id"]}.html',
    }


def _human_veto(registry, community_id, record):
    """Reason a human decision forbids an automatic binding, if any."""
    from src.services.community_review import same_community
    with registry.db() as db:
        if db.execute('SELECT 1 FROM rejected WHERE rid=? AND cid=?',
                      (record['id'], community_id)).fetchone():
            return '人工已拒绝该关联'
        admission = db.execute('SELECT payload FROM community_admission WHERE cid=?', (community_id,)).fetchone()
        if admission:
            payload = json.loads(admission[0])
            if payload.get('auto_review_locked') or payload.get('state') == 'excluded':
                return '目标小区已有人工排除或审核锁'
        for veto in db.execute('SELECT c.payload AS decision,s.* FROM review_candidates c '
                               'JOIN review_members m ON m.candidate_id=c.id JOIN sources s ON s.id=m.rid'):
            decision = json.loads(veto['decision'])
            if (decision.get('auto_review_locked') or decision.get('state') == 'excluded') \
                    and same_community(record, dict(veto)):
                return '同一小区身份已有人工审核决定'
    return None


def bind_source(registry, community, candidate, *, seed, method='manual', evidence=None):
    """Create the Xingfuli source and attach it to the internal community.

    The registry's automatic branch refuses a differing address outright; a
    platform address is written in its own wording, so a position match has to
    be able to bind. The human decisions that branch protects are checked here
    instead, so no explicit decision is overridden.
    """
    record = registry.ingest(dict(
        source='xingfuli', source_kind='community', source_id=candidate['neighborhood_id'],
        name=candidate['name'], address=candidate['address'],
        coordinate_system=candidate['coordinate_system'],
        longitude=candidate['longitude'], latitude=candidate['latitude'],
        seed_listing_id=seed, source_url=list_url(seed),
        homepage_url=candidate.get('homepage_url'), discovered_via=candidate.get('discovered_via'),
        # The generic similarity branch of auto_associate would bind a phase
        # variant; this provider only binds through the checked evidence above.
        auto_association_disabled=True, verified_at=now()))
    if method == 'auto':
        veto = _human_veto(registry, community['community_id'], record)
        if veto:
            raise ValueError(veto)
    registry.associate(record['id'], community['community_id'], method=method,
                       evidence=evidence or ['人工确认'])
    return record['id']


def protected(registry, community_id):
    """True when a human already decided this community's rental source."""
    with registry.db() as db:
        if db.execute('SELECT 1 FROM rejected WHERE cid=?', (community_id,)).fetchone():
            return True
        row = db.execute("SELECT 1 FROM sources WHERE cid=? AND status='matched' AND source IN ('fang','xingfuli')",
                         (community_id,)).fetchone()
    return bool(row)


def active_source(registry, community_id):
    from src.services.rental_reference.providers import active_sources
    return active_sources(registry).get(community_id)


def _name_related(query, platform_name):
    left, right = normalized(query), normalized(platform_name)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def auto_discover(registry, client, communities, *, budget=AUTO_SEARCH_BUDGET, cancel=None):
    """Bind the Xingfuli sources whose identity the platform proves.

    Only strong evidence binds automatically: the exact internal name plus an
    agreeing address or position and no phase or district conflict. Everything
    else stays unbound, and the on-demand probe handles it.
    """
    report = {'checked': 0, 'matched': 0, 'pending': 0, 'failed': 0, 'deferred': 0}
    for community in communities:
        if cancel is not None and cancel.is_set():
            break
        community_id = community['community_id']
        if protected(registry, community_id) or active_source(registry, community_id):
            continue
        report['checked'] += 1
        matched = False
        for name in community_names(community)[:2]:
            # The second-hand channel names the whole community; the rent
            # channel can answer with a phase identity instead.
            for channel in ('second_hand', 'rent'):
                if client.request_count >= budget:
                    report['deferred'] += 1
                    return report
                try:
                    groups = client.search(name, channel)
                except ValueError as exc:
                    logger.warning('Xingfuli auto search failed community_id=%s channel=%s error=%s',
                                   community_id, channel, exc)
                    if '冷却' in str(exc):
                        report['deferred'] += 1
                        return report
                    continue
                matches = {nid: group for nid, group in groups.items()
                           if _name_related(name, group['name'])}
                for neighborhood_id, group in matches.items():
                    if client.request_count >= budget:
                        report['deferred'] += 1
                        return report
                    try:
                        homepage = client.homepage(neighborhood_id)
                    except ValueError as exc:
                        logger.warning('Xingfuli auto homepage failed community_id=%s id=%s error=%s',
                                       community_id, neighborhood_id, exc)
                        continue
                    candidate = candidate_from_homepage(homepage, discovered_via=channel)
                    judgement = evaluate(community, candidate)
                    if not judgement['strong']:
                        report['pending'] += 1
                        continue
                    seed = next(iter(group['seeds']), None)
                    if not seed:
                        seed = candidate['seeds'][0] if candidate['seeds'] else None
                        if seed:
                            try:
                                if client.listing_owner(seed) != neighborhood_id:
                                    seed = None
                            except ValueError:
                                seed = None
                    if not seed:
                        report['pending'] += 1
                        continue
                    try:
                        bind_source(registry, community, candidate, seed=seed, method='auto',
                                    evidence=[*judgement['evidence'], '平台主页与目录证据一致'])
                    except ValueError as exc:
                        report['failed'] += 1
                        logger.warning('Xingfuli auto bind failed community_id=%s error=%s',
                                       community_id, exc)
                        continue
                    report['matched'] += 1
                    matched = True
                    break
                if matched:
                    break
            if matched:
                break
    return report


def dump_state(payload):
    return dump(payload)
