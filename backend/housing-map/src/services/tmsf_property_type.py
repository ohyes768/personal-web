"""Property facts shared by directory collection and the maintenance CLI."""
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


def fetch_property_facts(client, community_id, names, *, timeout=15):
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
                address=info.get('address') or '')
