# 修正新房地图展示统计

## 用户确认的需求
新房以项目点位展示，不要求地块边界；已在地图标出的新房不应计入未展示。

## 验收标准
- 有效收录且 map_status=displayed 的新房，即使没有轮廓，也计入 stats.displayed。
- 缺坐标、坐标待核、围栏外等既有未展示原因继续生效。
- 二手及未知类型沿用轮廓统计规则；售完项目按有效 second_hand 身份处理。
- 不修改数据、地图渲染方式、收录或定位规则，仅修正统计及相关契约注释。

## 实施与验证
先用真实 registry API 测试复现新房被误计为边界待补，再在 routes.py 的边界统计判断中排除 market_state=new_house。同步类型注释和规范，运行新房、地图 API、准入与边界相关测试。

## 验证结果
- 回归测试先失败：带有效坐标的新房被错误计入 missing_boundary。
- 修正后 test_newhouse_map_api.py、test_api.py、test_community_admission_api.py、test_boundary_workflow.py：55 passed（2 条依赖弃用提示）。Windows basetemp 使用项目盘独立目录。
- NAS 当前 registry + 有效轮廓只读重算：admitted=151、displayed=151、hidden={}。
- 前端只更新类型注释，接口形状及渲染逻辑不变。
- 代码与相关契约已验证，部署后生效。
