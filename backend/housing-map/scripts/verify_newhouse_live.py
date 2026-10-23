"""只读实测：本机直接抓透明售房网新房索引与详情，验证解析器假设。不写任何数据。"""
import sys
sys.path.insert(0, '.')
from src.services.tmsf_fetcher import TmsfClient
from src.services.tmsf_property_type import (parse_project_index, project_identity,
                                             fetch_project_facts_by_id, PROJECT_INDEX_URL)

NAMES = ['春来晴翠园', '泊玺骏庐', '月澜雅颂里']

client = TmsfClient()
try:
    rows = parse_project_index(client.fetch_text(PROJECT_INDEX_URL, 20))
    bj = [r for r in rows if (r.get('districtname') or '').removesuffix('区') == '滨江']
    print(f'索引项目总数 {len(rows)}，滨江 {len(bj)}')
    state = {2: '在售', 3: '尾盘', 4: '售完', 5: '待售'}
    selling = [r for r in bj if state.get(r.get('propertystateid')) in {'在售', '尾盘', '待售'}]
    print(f'滨江在售/尾盘/待售 {len(selling)}')
    for target in NAMES:
        hit = [r for r in bj if any(target in n for n in (r.get('propertyname') or '').replace('（', '(').replace('）', ')').split('('))]
        if not hit:
            print(f'{target}: 索引未找到')
            continue
        project = hit[0]
        identity = project_identity(project)
        print(f'{target}: propertyid={project["propertyid"]} siteid={project["siteid"]} 状态={identity["project_sale_status"]}')
        try:
            facts = fetch_project_facts_by_id(client, siteid=project['siteid'], propertyid=project['propertyid'],
                                              names=[n for n in (project.get('propertyname') or '').split('(') if n],
                                              district='滨江')
            print(f'  用途={facts["property_type"]} 状态={facts["project_sale_status"]} 区域={facts["address_district"]}')
            print(f'  地址={facts.get("address") or facts.get("address_error")}')
        except Exception as exc:
            print(f'  详情失败: {getattr(exc, "code", type(exc).__name__)}: {exc}')
finally:
    client.close()
