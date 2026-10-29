"""市场身份、项目证据与位置可信度的只读投影。

只投影已有证据：未知就是未知，售完按有效状态回到二手房，项目编号与小区编号始终分离。
"""

# 只有现场 POI 核验或人工发布的位置算已核验；历史快照坐标不能声称做过新鲜核验。
VERIFIED_POSITION_SOURCES = {'amap', 'manual'}


def project_view(records):
    """新房项目证据。项目优先取项目类来源，其次取社区来源上已核实的项目身份。"""
    candidates = [r for r in records if r.get('project_id')]
    if not candidates:
        return None
    record = next((r for r in candidates if r.get('source_kind') == 'project'), candidates[0])
    return {
        'project_id': str(record.get('project_id')),
        'project_name': record.get('project_name'),
        'sale_status': record.get('project_sale_status'),
        'identity_url': record.get('market_state_url') or record.get('project_url'),
        'captured_at': record.get('market_state_captured_at'),
    }


def position_evidence_view(community, records, coordinate=None):
    """位置来源与核验状态。没有核验证据就说没有，不按来源名称猜可信度。"""
    evidence = community.get('coordinate_evidence') or {}
    source = evidence.get('source')
    if not source:
        for record in records:
            candidate = (record.get('coordinate_evidence') or {}).get('source')
            if candidate:
                source = candidate
                break
    address = ((coordinate or {}).get('formatted_address')
               or community.get('position_formatted_address')
               or community.get('geographic_address')
               or community.get('address'))
    return {
        'source': source,
        'verified': source in VERIFIED_POSITION_SOURCES,
        'address': address or None,
    }
