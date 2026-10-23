"""TMSF-only admission. Pure projection; historical decisions are never rewritten."""
from src.services.community_address import effective_address
from src.services.community_listing import listing_gate
from src.services.community_registry import normalized
from src.services.residential_classifier import RESIDENTIAL_TYPES, NON_RESIDENTIAL_TYPES

VERSION = 'tmsf-directory-v1'
KEY = 'directory_flow_version'


def enabled(db):
    row = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
    return bool(row and row[0] == VERSION)


def eligibility(community, records, facts=None, admission=None):
    facts = facts or {}
    admission = admission or {}
    def result(code, reason, *, incomplete=False, prop=None):
        return dict(admission_state='admitted' if code == 'eligible' else 'excluded',
                    qualification=code, exclusion_reason=reason, effective_property_type=prop,
                    facts_state='incomplete' if incomplete else 'complete')
    if community.get('deleted') or community.get('merged_to'):
        return result('inactive', '小区已删除或合并')
    if admission.get('decision_kind') == 'manual' and (admission.get('state') == 'excluded' or admission.get('auto_review_locked')):
        return result('manual_exclusion', admission.get('reason') or '人工暂不收录')
    records = [r for r in records if r['source'] == 'tmsf' and r.get('status') != 'ignored']
    if not records:
        return result('missing_tmsf', '缺少透明售房网资料，待补充', incomplete=True)
    names = {normalized(n) for n in [community.get('community_name'), community.get('community_alias'), *community.get('aliases', [])] if n}
    if names and any(r.get('method') != 'manual' and normalized(r['name']) not in names and not names.intersection(normalized(n) for n in r.get('aliases', [])) for r in records):
        return result('identity_conflict', '透明售房网名称与小区身份不一致，待补资料', incomplete=True)
    area = normalized(community.get('district')).removesuffix('区')
    if not area or any(normalized(r.get('district')).removesuffix('区') != area for r in records):
        return result('district_missing', '区域资料缺失或不一致，待补充', incomplete=True)
    types = set()
    for record in records:
        prop = record.get('property_type')
        if not prop and not record.get('property_type_checked_at') and record.get('source_kind') != 'project':
            prop = facts.get(str(record['source_id']), {}).get('property_type')
        if record.get('property_type_conflict'):
            return result('type_conflict', '透明售房网用途证据冲突，待补资料', incomplete=True)
        if not prop:
            return result('type_missing', '透明售房网用途资料缺失，待补充', incomplete=True)
        types.add(prop)
    if not types <= RESIDENTIAL_TYPES:
        text = ' / '.join(sorted(types))
        if types <= NON_RESIDENTIAL_TYPES:
            return result('non_residential', f'透明售房网用途为{text}，不收录')
        return result('type_uncertain', f'透明售房网用途为{text}，住宅用途不明确，暂不收录', incomplete=True)
    verified = [r for r in records if not r.get('address_verification_pending')]
    actual_address = community.get('address') if community.get('address_origin') == 'manual' else ''
    if not effective_address(actual_address, verified):
        return result('address_missing', '实际地址资料缺失或待核实，暂不收录', incomplete=True)
    state, reason = listing_gate(records, community)
    if state:
        return result('listing_low' if state == 'excluded' else 'listing_missing', reason, incomplete=state != 'excluded')
    if not all(r.get('market_state') == 'new_house' or isinstance(r.get('listing_count'), int) or
               isinstance(community.get('listing_count'), int) for r in records):
        return result('listing_missing', '二手房挂牌数量或新房身份证据缺失，待补充', incomplete=True)
    return result('eligible', '', prop=next(r['property_type'] for r in records if r.get('property_type') in RESIDENTIAL_TYPES)
                  if any(r.get('property_type') in RESIDENTIAL_TYPES for r in records) else sorted(types)[0])
