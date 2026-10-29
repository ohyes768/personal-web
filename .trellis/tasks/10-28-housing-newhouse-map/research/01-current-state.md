# 现状证据

2026-10-28，基线4d53b13，工作区起始干净。用户明确目标为新房与附近二手房比较，选择同地图与房源类型切换，并授权开任务。

- apps/housing-map/src/components/community/CatalogFilters.tsx:36已有new_house/second_hand筛选。
- DirectoryCards.tsx:35已有new_house/second_hand/unknown文案与项目ID显示。
- src/lib/types.ts的Community尚无market_state/project字段；PriceInfo为二手挂牌/签约价格。
- backend/housing-map/src/api/routes.py:81的_assemble_community组装price/坐标/轮廓，未完整投影市场身份。
- apps/housing-map/src/app/page.tsx:410附近以名称、区域、物业类型筛选，尚无市场类型切换。
- BinjiangMap.tsx:315起统一按二手价格取色，:347附近无轮廓画100米方块＋问号。
- community-enrichment spec规定显式销售状态决定有效market_state，售完转二手；项目ID独立；售楼处/门口等不能冒充项目定位；新房价格不能进入二手指标；无坐标保留收录但不展示。

因此不能只加星形图标：还需从有效身份到API、筛选、图层、详情和统计贯通。任务不承诺新增采集；当前是否已有可用项目价格需实施前核实，无则展示暂无价格。聚合及定位可信度沿用现有证据/地图能力评估，不假设已具备。

默认设计值：全部模式；新字标记；附近1500米直线；未知只在全部；不新增顶层tab；无可靠轮廓只画点；只有售楼处不画项目点。均在规划中显式记录，便于用户评审。
