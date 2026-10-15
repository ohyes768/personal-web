"""Property facts shared by directory collection and the maintenance CLI."""
import json
import re

from src.services.community_registry import normalized
from src.services.tmsf_fetcher import BASE_URL, input_value_by_id, parse_index_page, strip_tags


def normalize_property_type(value):
    # Preserve ambiguous/mixed values; never infer 住宅 from a substring such as 非住宅.
    text = strip_tags(value or '').strip()
    return text if text and len(text) <= 100 else None


def extract_property_type(html):
    value = input_value_by_id(html, 'managetypename_auto')
    if value:
        return normalize_property_type(value)
    match = re.search(r'物业类型\s*[:：]?\s*([^\s]+)', strip_tags(html))
    return normalize_property_type(match.group(1)) if match else None


def fetch_community_facts(client, community_id, names, *, timeout=15):
    if not str(community_id).isdigit():
        raise ValueError('无效的透明售房网小区 ID')
    url = f'{BASE_URL}/esf/xq_indexnew_{community_id}.htm'
    html = client.fetch_text(url, timeout)
    info = parse_index_page(html)
    title = re.search(r'<title>\s*(.*?)\s*-小区详情', html, re.I | re.S)
    observed_names = [info.get('community_name'), input_value_by_id(html, 'communityname_auto'),
                      strip_tags(title.group(1)) if title else None]
    if not {normalized(n) for n in observed_names if n} & {normalized(n) for n in names if n}:
        raise ValueError('详情页面无法确认目标小区')
    property_type = extract_property_type(html)
    if not property_type:
        raise ValueError('详情页面缺少物业类型')
    return dict(property_type=property_type, property_type_url=url,
                address=info.get('address') or '', address_district=info.get('district'), market_state='second_hand',
                listing_count=info.get('listing_count'), listing_count_error=None)


PROJECT_INDEX_URL = f'{BASE_URL}/include/hzweb/index_search_center_property.js'


def project_names(value):
    # The public index explicitly supplies marketing/legal aliases in parentheses.
    return [n.strip() for n in re.split(r'[()（）]', value or '') if n.strip()]


def parse_project_index(script):
    match = re.search(r'\bvar\s+data_auto\s*=\s*', script)
    if not match:
        raise ValueError('新房项目索引无法读取')
    rows, _ = json.JSONDecoder().raw_decode(script[match.end():])
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('新房项目索引格式异常')
    return rows


def find_project(rows, names, district):
    names = {normalized(n) for n in names if n}
    hits = {str(r.get('propertyid')): r for r in rows
            if normalized(r.get('districtname')).removesuffix('区') == normalized(district).removesuffix('区')
            and names & {normalized(n) for n in project_names(r.get('propertyname'))}}
    if len(hits) != 1:
        raise ValueError('新房项目身份缺失或存在同名分期歧义')
    project = next(iter(hits.values()))
    if not all(str(project.get(k, '')).isdigit() for k in ('propertyid', 'siteid')):
        raise ValueError('新房项目编号无效')
    return project


def project_market_state(status):
    return 'new_house' if status in {'在售', '尾盘', '待售'} else 'second_hand' if status == '售完' else 'unknown'


def effective_market_state(record):
    # Repair legacy sold-out promotions at read time without changing audit history.
    if record.get('market_state') == 'new_house' and record.get('project_sale_status') == '售完':
        return 'second_hand'
    return record.get('market_state')


def project_identity(project):
    url = f"{BASE_URL}/newhouse/property_{project['siteid']}_{project['propertyid']}_infoUpgrade.htm"
    status = {2: '在售', 3: '尾盘', 4: '售完', 5: '待售'}.get(project.get('propertystateid'), '未知')
    return dict(market_state=project_market_state(status), market_state_url=PROJECT_INDEX_URL,
                project_id=str(project['propertyid']), project_name=project_names(project.get('propertyname'))[-1],
                project_aliases=project_names(project.get('propertyname')),
                project_url=url,
                project_sale_status=status)


def class_text(html, class_name):
    match = re.search(r'<(?:div|span)\b[^>]*class=["\'][^"\']*\b' + re.escape(class_name) +
                      r'\b[^"\']*["\'][^>]*>(.*?)</(?:div|span)>', html, re.S | re.I)
    return strip_tags(match.group(1)).strip() if match else ''


def fetch_project_facts(client, names, district, *, projects=None, timeout=15):
    projects = projects if projects is not None else parse_project_index(client.fetch_text(PROJECT_INDEX_URL, timeout))
    project = find_project(projects, names, district)
    url = project_identity(project)['project_url']
    html = client.fetch_text(url, timeout)
    observed_name = class_text(html, 'house_float_name_title')
    district_match = re.search(r'<a\b[^>]*id=["\']districtname["\'][^>]*>(.*?)</a>', html, re.S)
    observed_district = strip_tags(district_match.group(1)).removesuffix('楼盘').removesuffix('区') if district_match else ''
    if normalized(observed_name) not in {normalized(n) for n in project_names(project.get('propertyname'))} or observed_district != district.removesuffix('区'):
        raise ValueError('新房详情页面无法确认目标项目和区域')
    prop = normalize_property_type(class_text(html, 'house_float_name_tips_grey'))
    match = re.search(r'楼盘地址\s*</div>\s*<div\b[^>]*>(.*?)</div>', html, re.S)
    address = strip_tags(match.group(1)).strip() if match else ''
    if not prop or not address:
        raise ValueError('新房详情缺少用途或实际地址')
    status = class_text(html, 'house_float_name_tips_grey999') or project_identity(project)['project_sale_status']
    return dict(property_type=prop, property_type_url=url, address=address, address_district=observed_district,
                market_state=project_market_state(status), market_state_url=url,
                project_id=str(project['propertyid']), project_name=observed_name,
                project_aliases=project_names(project.get('propertyname')),
                project_sale_status=status)


def fetch_property_facts(client, community_id, names, *, timeout=15, projects=None, district='滨江'):
    if not str(community_id).isdigit():
        raise ValueError('无效的透明售房网小区 ID')
    try:
        return fetch_community_facts(client, community_id, names, timeout=timeout)
    except Exception:
        # Project IDs are looked up independently; never reuse an ESF community ID.
        return fetch_project_facts(client, names, district, projects=projects, timeout=timeout)
