"""TMSF-only admission. Pure projection; historical decisions are never rewritten."""
from src.services.community_address import effective_address
from src.services.community_listing import listing_gate
from src.services.community_registry import normalized
from src.services.residential_classifier import RESIDENTIAL_TYPES, NON_RESIDENTIAL_TYPES
from src.services.use_review_policy import (
    CHECKED, CONFLICT, RULE_VERSION, UNCERTAIN_RESULT, compare, contrary_evidence, tmsf_property_types,
    use_review_view,
)

VERSION = 'tmsf-directory-v1'
KEY = 'directory_flow_version'


def enabled(db):
    row = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
    return bool(row and row[0] == VERSION)


def eligibility(community, records, facts=None, admission=None):
    from src.services.collection_pipeline import active, position_gate, selected_review
    pipeline = active(community)
    facts = facts or {}
    admission = admission or {}
    def result(code, reason, *, incomplete=False, prop=None):
        status = dict(admission_state='admitted' if code == 'eligible' else 'excluded',
                    qualification=code, exclusion_reason=reason, effective_property_type=prop,
                    facts_state='incomplete' if incomplete else 'complete')
        if pipeline:
            status['workflow_state'] = 'admitted' if code == 'eligible' else 'pending' if incomplete else 'excluded'
        return status
    if community.get('deleted') or community.get('merged_to'):
        return result('inactive', '小区已删除或合并')
    records = [r for r in records if r['source'] == 'tmsf' and r.get('status') != 'ignored']
    # 高德分类只是第二来源证据：人工用途决定优先，出现新的相反证据才回到待审核。
    use_decision = admission.get('use_rule') == RULE_VERSION and admission.get('use_decision')
    if use_decision:
        contrary = contrary_evidence(admission, records, selected_review(community, records) if pipeline else use_review_view(community))
        if contrary:
            return result('use_conflict', f'用途分类冲突待人工审核：{contrary}', incomplete=True)
        if admission['use_decision'] != 'residential':
            return result('manual_exclusion', admission.get('reason') or '人工确认非住宅，不收录')
    if (admission.get('decision_kind') == 'manual' and not use_decision
            and (admission.get('state') == 'excluded' or admission.get('auto_review_locked'))):
        return result('manual_exclusion', admission.get('reason') or '人工暂不收录')
    if not records:
        return result('missing_tmsf', '缺少透明售房网资料，待补充', incomplete=True)
    from src.services.source_collection_state import collection_resolution
    if any(collection_resolution(r)['state'] == 'identity_conflict' for r in records):
        return result('identity_conflict', '来源项目身份不一致，待核对身份', incomplete=True)
    names = {normalized(n) for n in [community.get('community_name'), community.get('community_alias'), *community.get('aliases', [])] if n}
    if names and any(r.get('method') != 'manual' and normalized(r['name']) not in names and not names.intersection(normalized(n) for n in r.get('aliases', [])) for r in records):
        return result('identity_conflict', '透明售房网名称与小区身份不一致，待补资料', incomplete=True)
    area = normalized(community.get('district')).removesuffix('区')
    if not area or any(normalized(r.get('district')).removesuffix('区') != area for r in records):
        return result('district_missing', '区域资料缺失或不一致，待补充', incomplete=True)
    if pipeline:
        from src.services.use_review_scope import auto_review_skip_reason
        region = auto_review_skip_reason({**community, 'sources': records, 'admission': {}, 'qualification': None})
        if area not in {'滨江', '萧山'} or (region and region.startswith('区域异常')):
            return result('region_conflict', region or '楼盘不在支持的区域内', incomplete=True)
    human_prop = None
    if use_decision:
        # 人工确认只覆盖用途门槛，区域、地址、挂牌等门槛照常执行。
        human_prop = admission.get('property_type') or '住宅'
        types = {human_prop}
    else:
        types = set()
        for record, prop in zip(records, tmsf_property_types(records, facts)):
            if record.get('property_type_conflict'):
                return result('type_conflict', '透明售房网用途证据冲突，待补资料', incomplete=True)
            if not prop:
                return result('type_missing', '透明售房网用途资料缺失，待补充', incomplete=True)
            types.add(prop)
        # 高德证据永不自动收录或排除：只制造待审核冲突。
        review = selected_review(community, records) if pipeline else use_review_view(community)
        outcome = compare(types, review.get('category') if review.get('state') == CHECKED else None)
        if outcome == CONFLICT:
            return result('use_conflict', '透明售房网与高德用途分类冲突，待人工审核', incomplete=True)
        if outcome == UNCERTAIN_RESULT:
            return result('use_uncertain', '两来源用途尚不能确定，请人工确认' if pipeline else '住宅用途待确认，暂不收录', incomplete=True)
        if not types <= RESIDENTIAL_TYPES:
            text = ' / '.join(sorted(types))
            from src.services.use_review_scope import EXPLICIT_NON_RESIDENTIAL_TYPES
            if types <= (EXPLICIT_NON_RESIDENTIAL_TYPES if pipeline else NON_RESIDENTIAL_TYPES):
                return result('non_residential', f'透明售房网用途为{text}，不收录')
            reason = f'透明售房网用途为{text}，待查询高德地点类型并确认用途' if pipeline else f'透明售房网用途为{text}，住宅用途不明确，暂不收录'
            if pipeline:
                from src.services.directory_position_state import position_view
                position = position_view(community, records)
                if position.get('reference_candidates'):
                    reason = f'透明售房网用途为{text}，已有高德相关地点信息，请人工核对用途'
                elif position.get('query_history'):
                    reason = f"透明售房网用途为{text}，{position['query_history']['message']}"
                elif position['state'] == 'not_found':
                    reason = f'透明售房网用途为{text}，高德已查询但未找到主体地点，可补充别名后重查'
                elif position['state'] == 'error':
                    reason = f'透明售房网用途为{text}，高德查询失败，请重查后确认用途'
                elif position['state'] == 'review':
                    reason = f'透明售房网用途为{text}，请先确认高德候选主体地点，再判断用途'
            return result('type_uncertain', reason, incomplete=True)
    if pipeline:
        gate = position_gate(community, records, human_use=bool(use_decision))
        if gate:
            return result(*gate, incomplete=True)
    from src.services.community_address import admission_address
    if not admission_address(community, records)['valid']:
        return result('address_missing', '实际地址资料缺失或待核实，暂不收录', incomplete=True)
    state, reason = listing_gate(records, community)
    if state:
        return result('listing_low' if state == 'excluded' else 'listing_missing', reason, incomplete=state != 'excluded')
    if not all(r.get('market_state') == 'new_house' or isinstance(r.get('listing_count'), int) or
               isinstance(community.get('listing_count'), int) for r in records):
        return result('listing_missing', '二手房挂牌数量或新房身份证据缺失，待补充', incomplete=True)
    if human_prop:
        prop = human_prop
    elif any(r.get('property_type') in RESIDENTIAL_TYPES for r in records):
        prop = next(r['property_type'] for r in records if r.get('property_type') in RESIDENTIAL_TYPES)
    else:
        prop = sorted(types)[0]
    return result('eligible', '', prop=prop)
