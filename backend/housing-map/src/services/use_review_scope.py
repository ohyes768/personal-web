"""Automatic use-review scope; manual lookups remain available for every identity."""
import re

from src.services.residential_classifier import NON_RESIDENTIAL_TYPES
from src.services.use_review_policy import RULE_VERSION


_ADDRESS_DISTRICT = re.compile(r'(上城|下城|江干|拱墅|西湖|滨江|萧山|余杭|临平|钱塘|富阳|临安)区')
# These extra types only affect automatic queries, never admission rules.
EXPLICIT_NON_RESIDENTIAL_TYPES = NON_RESIDENTIAL_TYPES | {'商铺', '厂房'}


def auto_review_skip_reason(row):
    """Explain an automatic skip without changing use evidence or admission."""
    admission = row.get('admission') or {}
    if ((admission.get('use_rule') == RULE_VERSION and admission.get('use_decision'))
            or row.get('qualification') == 'manual_exclusion'
            or (admission.get('decision_kind') == 'manual' and admission.get('auto_review_locked'))):
        return '已有人工用途决定或人工排除，按需手动查询'
    district = (row.get('district') or '').removesuffix('区')
    addresses = [row.get('source_address', row.get('address')) or '']
    if row.get('address_origin') != 'manual':
        addresses.extend(r.get('address') or '' for r in row.get('sources', []) if r.get('source') == 'tmsf')
    for address in addresses:
        for area in _ADDRESS_DISTRICT.findall(address):
            if district and area != district:
                return f'区域异常：地址标注{area}区，与目录{district}区不一致，请先核实地址'
    if (row.get('qualification') in {'type_missing', 'type_conflict'}
            or any(r.get('property_type_conflict') for r in row.get('sources', []) if r.get('source') == 'tmsf')):
        return None
    types = set(row.get('property_types') or [])
    if types and types <= EXPLICIT_NON_RESIDENTIAL_TYPES:
        return '透明售房网用途明确为非住宅，按需手动查询'
    if row.get('admission_state') == 'admitted' and (row.get('position') or {}).get('state') not in {'matched', 'manual'}:
        return '已收录住宅尚未完成定位，请先补全定位'
    return None
