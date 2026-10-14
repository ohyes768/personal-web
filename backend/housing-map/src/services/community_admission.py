"""Residential admission is independent of source identity and collection eligibility."""
import json
import math
import sqlite3
from pathlib import Path

from src.services.community_address import effective_address
from src.services.community_listing import listing_gate

from src.core.boundary import is_in_scope, is_in_xiaoshan_border
from src.services.community_filters import is_real_community
from src.services.community_registry import dump, now
from src.services.residential_classifier import RESIDENTIAL_TYPES, classify_sources


def property_facts(data_dir):
    path = Path(data_dir) / 'property_types.json'
    if not path.exists():
        return {}
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    return {str(k): v for k, v in report.items() if isinstance(v, dict)} if isinstance(report, dict) else {}


def effective_type(records, facts):
    for record in records:
        if record['source'] == 'tmsf':
            prop = record.get('property_type')
            if not record.get('property_type_checked_at') and not prop:
                prop = facts.get(record['source_id'], {}).get('property_type')
            if prop in RESIDENTIAL_TYPES:
                return prop
    return '住宅'  # A consistent residential Fang classification uses the common label.


def migrate_admission(store, data_dir):
    """One-time, backed-up initialization of existing masters; no new auto admissions."""
    with store.db() as db:
        if db.execute("SELECT 1 FROM meta WHERE key='admission_schema_version'").fetchone():
            return
    backup = Path(data_dir) / 'directory-backup' / 'community_registry-before-admission.sqlite3'
    backup.parent.mkdir(exist_ok=True)
    if not backup.exists():
        with sqlite3.connect(store.path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
    facts = property_facts(data_dir)
    with store.db() as db:
        if db.execute("SELECT 1 FROM meta WHERE key='admission_schema_version'").fetchone():
            return
        for row in db.execute('SELECT * FROM communities'):
            if db.execute('SELECT 1 FROM community_admission WHERE cid=?', (row['id'],)).fetchone():
                continue
            records = [store._source(r) for r in db.execute("SELECT * FROM sources WHERE cid=? AND status='matched'", (row['id'],))]
            classification = classify_sources(records, facts)
            state = 'admitted' if classification == 'residential' else 'excluded' if classification == 'non_residential' else 'pending'
            if row['deleted'] or row['merged_to']:
                state = 'excluded'
            value = dict(state=state, decision_kind='migration', property_type=effective_type(records, facts) if state == 'admitted' else None,
                         revision=1, auto_review_locked=bool(row['deleted']), reason='旧主档用途证据初始化',
                         evidence=records, decided_at=now(), rule_version='admission-migration-v1')
            db.execute('INSERT INTO community_admission VALUES (?,?)', (row['id'], dump(value)))
            store._event(db, row['id'], 'admission_migration', {'admission': value})
        db.execute("INSERT INTO meta VALUES ('admission_schema_version','1')")


def map_status(community, admission, coordinate=None, *, drop_ids=()):
    if community.get('deleted') or community.get('merged_to'):
        return 'inactive'
    if admission['state'] != 'admitted':
        return 'not_admitted'
    if community['community_id'] in drop_ids:
        return 'merged_duplicate'
    if not is_real_community(community):
        return 'check_name'
    coordinate = coordinate or community
    lng, lat = coordinate.get('longitude'), coordinate.get('latitude')
    if lng is None or lat is None:
        return 'missing_coordinates'
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lng, lat)):
        return 'check_coordinates'
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        return 'check_coordinates'
    address = coordinate.get('formatted_address', community.get('address')) or ''
    district = (community.get('district') or '').removesuffix('区')
    if district == '滨江' and '滨江区' not in address:
        return 'check_coordinates'
    if district == '萧山' and ('萧山区' not in address or not is_in_xiaoshan_border(lng, lat)):
        return 'check_coordinates'
    if '滨江区' not in address and '萧山区' not in address:
        return 'check_coordinates'
    if community.get('coordinate_system', 'gcj02') != 'gcj02':
        return 'check_coordinates'
    return 'displayed' if is_in_scope(lng, lat) else 'outside_scope'


def community_views(store, data_dir, *, deleted=False, coordinates=None, drop_ids=()):
    if coordinates is None:
        coordinate_path = Path(data_dir) / 'binjiang_coordinates.json'
        coordinates = json.loads(coordinate_path.read_text(encoding='utf-8-sig')) if coordinate_path.exists() else {}
    facts = property_facts(data_dir)
    # One consistent read transaction; opening one connection per master slows inventory queries.
    with store.db() as db:
        sources = [store._source(r) for r in db.execute('SELECT * FROM sources ORDER BY source,sid')]
        communities = [store._community(r) for r in db.execute('SELECT * FROM communities WHERE deleted=? AND merged_to IS NULL ORDER BY id', (int(deleted),))]
        admissions = {r['cid']: json.loads(r['payload']) for r in db.execute('SELECT * FROM community_admission')}
    result = []
    for community in communities:
        cid = community['community_id']
        coordinate = coordinates.get(cid)
        if community.get('longitude') is not None and community.get('latitude') is not None:
            coordinate = {**community, 'formatted_address': community.get('address', '')}
        records = [r for r in sources if r['community_id'] == cid and r['status'] == 'matched']
        admission = admissions.get(cid, store.pending_admission())
        classification = classify_sources(records, facts)
        # Existing migrated/automatic admissions lose display eligibility on new conflicting evidence.
        conflict = admission['state'] == 'admitted' and classification != 'residential'
        effective_admission = admission
        if conflict and admission['decision_kind'] != 'manual':
            effective_admission = {**admission, 'state': 'pending'}
        address = effective_address(community.get('address'), records)
        listing_state, listing_reason = listing_gate(records, community)
        if listing_state and admission['state'] != 'excluded':
            effective_admission = {**effective_admission, 'state': listing_state}
        if not address:
            effective_admission = {**effective_admission, 'state': 'excluded'}
        prop = None
        if effective_admission['state'] == 'admitted':
            prop = admission.get('property_type') if admission['decision_kind'] == 'manual' else effective_type(records, facts)
        result.append({**community, 'address': address, 'address_missing': not bool(address), 'exclusion_reason': '缺少有效地址' if not address else listing_reason, 'admission': admission, 'admission_state': effective_admission['state'],
                       'admission_conflict': conflict, 'residential_state': classification,
                       'effective_property_type': prop,
                       'map_status': map_status(community, effective_admission, coordinate, drop_ids=drop_ids)})
    return result
