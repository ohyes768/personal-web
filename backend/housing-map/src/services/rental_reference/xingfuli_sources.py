"""Turn a discovered Xingfuli community into a rental source.

Legacy automatic binding needs an exact name and matching address or position.
The complete, unique-candidate probe may also accept an exact name when
coordinates cannot be compared, or a contained name within 100 meters without
phase qualifiers. A human may confirm other similar names, but never a phase
conflict or a different district. A keyword search response is never evidence.
"""
from __future__ import annotations

import json
import logging
import math

from src.services.community_registry import normalized, now
from src.services.rental_reference.providers import rejected_rental_communities
from src.services.xingfuli_discovery import CHANNEL_ORDER, address_district, phase_of, without_community_type_label
from src.services.xingfuli_rentals import list_url

logger = logging.getLogger(__name__)
POSITION_LIMIT_METERS = 100
AUTO_SEARCH_BUDGET = 5


def community_names(community):
    return [n for n in [community.get('community_name'), community.get('community_alias'),
                        *(community.get('aliases') or [])] if n]


def rental_name_key(value):
    """Ignore middle dots and generic 小区 annotations; retain identity qualifiers."""
    return normalized(without_community_type_label(value)).translate(str.maketrans('', '', '·•・‧∙⋅･'))


def _distance_meters(a_lng, a_lat, b_lng, b_lat):
    dx = (a_lng - b_lng) * math.cos(math.radians(a_lat)) * 111320
    dy = (a_lat - b_lat) * 111320
    return math.hypot(dx, dy)


def _matches_name(names, platform_name):
    """How the platform name relates to the internal names."""
    platform = rental_name_key(platform_name)
    if not platform:
        return 'none'
    for name in names:
        if rental_name_key(name) == platform:
            return 'exact'
    if phase_of(platform_name):
        # A qualified platform name is a phase of the base community.
        return 'none'
    for name in names:
        internal = rental_name_key(name)
        if internal and (internal in platform or platform in internal):
            return 'partial'
    return 'none'


def evaluate(community, candidate, *, allow_name_only=False, allow_partial_name=False):
    """Judge identity; name-only acceptance requires caller-proven uniqueness.

    Only the probe checks search completeness and candidate uniqueness and may
    enable either relaxation. Legacy discovery keeps the default exact name
    and place-evidence requirement.
    """
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
    api_district = (candidate.get('district') or '').removesuffix('区')
    if api_district and api_district != internal_district:
        conflicts.append(f'平台区域为{api_district}，与目录区域{internal_district}不一致')

    same_address = bool(normalized(candidate.get('address'))) and \
        normalized(candidate.get('address')) == normalized(community.get('address'))
    same_position = False
    values = [candidate.get('longitude'), candidate.get('latitude'),
              community.get('longitude'), community.get('latitude')]
    comparable_position = candidate.get('coordinate_system') == community.get('coordinate_system') == 'gcj02' \
        and all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
    if comparable_position:
        same_position = _distance_meters(*values) <= POSITION_LIMIT_METERS
    if same_address:
        evidence.append('地址一致')
    elif same_position:
        evidence.append('位置接近（100米内）')
    else:
        gaps.append('缺少一致地址或位置证据')

    exact_identity = match == 'exact' and (
        same_address or same_position or (allow_name_only and not comparable_position))
    nearby_partial_identity = allow_partial_name and match == 'partial' and same_position \
        and not any(phase_of(name) for name in [*names, candidate.get('name')])
    strong = not conflicts and (exact_identity or nearby_partial_identity)
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
        'district': homepage.get('district', ''),
        'phase': phase_of(homepage['name']),
        'rent_total': homepage.get('rent_total'),
        'seeds': list(homepage.get('seeds') or []),
        'discovered_via': discovered_via,
        'homepage_url': f'https://m.xflapp.com/xiaoqu/hz-{homepage["neighborhood_id"]}.html',
    }


def _human_veto(registry, community_id, record, *, allow_reprocessed=False):
    """Reason a human decision forbids a binding, if any.

    The registry's own automatic branch compares two source records to find
    the decisions it must respect. A Xingfuli record is excluded from that
    comparison on purpose, so the decisions are read here instead: the
    rejected pairs, the community's admission lock and the community's review
    group. `allow_reprocessed` is the explicit re-processing path: a user who
    asks for the probe again may bind an unlinked source, but nothing is ever
    rebound silently.
    """
    with registry.db() as db:
        if not allow_reprocessed:
            if db.execute('SELECT 1 FROM rejected WHERE rid=? AND cid=?',
                          (record['id'], community_id)).fetchone():
                return '人工已拒绝该来源与该小区的关联'
            if community_id in rejected_rental_communities(db):
                return '人工已解除或拒绝该小区的租金来源'
        admission = db.execute('SELECT payload FROM community_admission WHERE cid=?', (community_id,)).fetchone()
        if admission:
            payload = json.loads(admission[0])
            if payload.get('auto_review_locked') or payload.get('state') == 'excluded':
                return '目标小区已有人工排除或审核锁'
        if record.get('status') not in {None, 'pending'}:
            return '该幸福里来源已有有效关联，请先核对'
        for row in db.execute('SELECT payload FROM review_candidates'):
            group = json.loads(row[0])
            if group.get('existing_cid') != community_id:
                continue
            if group.get('auto_review_locked') or group.get('state') == 'excluded':
                return '该小区已有人工审核决定'
    return None


def bind_source(registry, community, candidate, *, seed, method='manual', evidence=None,
                allow_reprocessed=False):
    """Create the Xingfuli source and attach it to the internal community.

    The platform address is kept in its own field: it is the source's own
    wording, so it must neither veto the binding (the registry refuses an
    automatic binding whose address differs from the directory address) nor
    become the community's address evidence. The address or position evidence
    of this contract decides instead, and the human decisions the registry's
    automatic branch protects are checked above.
    """
    record = registry.ingest(dict(
        source='xingfuli', source_kind='community', source_id=candidate['neighborhood_id'],
        name=candidate['name'], platform_address=candidate['address'],
        coordinate_system=candidate['coordinate_system'],
        longitude=candidate['longitude'], latitude=candidate['latitude'],
        seed_listing_id=seed, source_url=list_url(seed),
        homepage_url=candidate.get('homepage_url'), discovered_via=candidate.get('discovered_via'),
        # The generic similarity branch of auto_associate would bind a phase
        # variant; this provider only binds through the checked evidence above.
        auto_association_disabled=True, verified_at=now()))
    veto = _human_veto(registry, community['community_id'], record, allow_reprocessed=allow_reprocessed)
    if veto:
        raise ValueError(veto)
    registry.associate(record['id'], community['community_id'], method=method,
                       evidence=evidence or ['人工确认'])
    return record['id']


def protected(registry, community_id):
    """True when a human already decided this community's rental source."""
    with registry.db() as db:
        if community_id in rejected_rental_communities(db):
            return True
        row = db.execute("SELECT 1 FROM sources WHERE cid=? AND status='matched' AND source IN ('fang','xingfuli')",
                         (community_id,)).fetchone()
    return bool(row)


def has_source(registry, community_id, *, xingfuli_only=False):
    """True when the community already has a confirmed rental source."""
    with registry.db() as db:
        row = db.execute("SELECT 1 FROM sources WHERE cid=? AND status='matched' AND source IN ('fang','xingfuli')"
                         + (" AND source='xingfuli'" if xingfuli_only else ''), (community_id,)).fetchone()
    return bool(row)


def active_source(registry, community_id):
    from src.services.rental_reference.providers import active_sources
    return active_sources(registry).get(community_id)


def _name_related(query, platform_name):
    left, right = normalized(query), normalized(platform_name)
    if not left or not right:
        return False
    return left == right or left in right or right in left


CURSOR_KEY = 'rental_xingfuli_auto_cursor'


def _ordered_communities(registry, communities):
    """The order the bounded budget should visit the communities in.

    One round can only afford a few requests. Without a cursor the same first
    community would consume every round and the remaining ones would never be
    discovered, so the round resumes after the last visited community.
    """
    with registry.db() as db:
        row = db.execute('SELECT value FROM meta WHERE key=?', (CURSOR_KEY,)).fetchone()
    cursor = row[0] if row else ''
    ids = [c['community_id'] for c in communities]
    if not cursor or cursor not in ids:
        return list(communities)
    start = (ids.index(cursor) + 1) % len(ids)
    return communities[start:] + communities[:start]


def _advance_cursor(registry, community_id):
    with registry.db() as db:
        db.execute('INSERT INTO meta(key,value) VALUES (?,?) '
                   'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (CURSOR_KEY, community_id))


def _verified_seed(client, candidate, neighborhood_id, *, budget):
    """A rent seed whose owner the platform pages prove.

    A search response nominates a seed but never proves it; the listing page
    and the same-neighborhood list do. A seed that belongs to another community
    would publish that community's rent under this one.
    """
    seeds = list(candidate.get('seeds') or [])
    for seed in dict.fromkeys(seeds):
        if client.request_count >= budget:
            return None
        try:
            if client.listing_owner(seed) != neighborhood_id:
                continue
            if client.request_count >= budget:
                return None
            if not client.listing_owner_from_list(seed, neighborhood_id):
                continue
        except ValueError as exc:
            logger.warning('Xingfuli seed verification failed id=%s seed=%s error=%s',
                           neighborhood_id, seed, exc)
            continue
        return seed
    return None


def _auto_match(registry, client, community, *, budget):
    """Try to bind one community; returns matched/pending/missing/failed/deferred."""
    community_id = community['community_id']
    found = False
    for name in community_names(community)[:2]:
        # Same identity channels as the on-demand probe. Rent search is not used
        # to find the neighborhood id.
        for channel in CHANNEL_ORDER:
            if client.request_count >= budget:
                return 'deferred'
            try:
                groups = client.search(name, channel)
            except ValueError as exc:
                logger.warning('Xingfuli auto search failed community_id=%s channel=%s error=%s',
                               community_id, channel, exc)
                if '冷却' in str(exc):
                    return 'deferred'
                continue
            for neighborhood_id, group in groups.items():
                if not _name_related(name, group['name']):
                    continue
                found = True
                if client.request_count >= budget:
                    return 'deferred'
                try:
                    homepage = client.community_info(neighborhood_id)
                except ValueError as exc:
                    logger.warning('Xingfuli auto homepage failed community_id=%s id=%s error=%s',
                                   community_id, neighborhood_id, exc)
                    continue
                candidate = candidate_from_homepage(homepage, discovered_via=channel)
                judgement = evaluate(community, candidate)
                if not judgement['strong']:
                    continue
                if client.request_count >= budget:
                    return 'deferred'
                try:
                    entry = client.rental_entry(neighborhood_id)
                except ValueError as exc:
                    logger.warning('Xingfuli auto entry failed community_id=%s id=%s error=%s',
                                   community_id, neighborhood_id, exc)
                    return 'failed'
                candidate.update(seeds=entry['seeds'], rent_total=entry['rent_total'])
                seed = _verified_seed(client, candidate, neighborhood_id, budget=budget)
                if not seed:
                    return 'deferred' if client.request_count >= budget else 'pending'
                try:
                    bind_source(registry, community, candidate, seed=seed, method='auto',
                                evidence=[*judgement['evidence'], '平台主页与目录证据一致'])
                except ValueError as exc:
                    logger.warning('Xingfuli auto bind failed community_id=%s error=%s',
                                   community_id, exc)
                    return 'failed'
                return 'matched'
    return 'pending' if found else 'missing'


def auto_discover(registry, client, communities, *, budget=AUTO_SEARCH_BUDGET, cancel=None):
    """Bind the Xingfuli sources whose identity the platform proves.

    Only strong evidence binds automatically: the exact internal name plus an
    agreeing address or position and no phase or district conflict. Everything
    else stays unbound, and the on-demand probe handles it.
    """
    report = {'checked': 0, 'matched': 0, 'pending': 0, 'missing': 0, 'failed': 0, 'deferred': 0}
    for community in _ordered_communities(registry, communities):
        if cancel is not None and cancel.is_set():
            break
        community_id = community['community_id']
        if protected(registry, community_id) or has_source(registry, community_id):
            continue
        outcome = _auto_match(registry, client, community, budget=budget)
        if outcome == 'deferred':
            # The budget ran out before this community was examined; it keeps
            # its place and is checked again in the next round.
            report['deferred'] += 1
            break
        report['checked'] += 1
        report[outcome] += 1
        _advance_cursor(registry, community_id)
    return report
