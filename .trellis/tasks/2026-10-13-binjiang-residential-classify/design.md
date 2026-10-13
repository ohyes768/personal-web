# 设计
## 复用
- scripts/fetch_tmsf_property_type.py 已提供 tmsf 物业类型。
- src/services/fang_rentals.py 的 enrich_detail 已记录 property_type（仅用于非住宅标记）。
## 改动
- 新增 src/services/residential_classifier.py：
  - 输入 tmsf property_types、fang 详情 samples、社区元数据
  - 输出每社区的 residential_state：residential / non_residential / pending / unknown
  - 规则：tmsf 住宅/别墅/排屋为 residential；fang 住宅/普通住宅为辅助证据；冲突或缺失为 pending
- 在 tmsf 目录采集后自动补抓缺失物业类型；fang 详情页抓取小区 ID 类型。
## 风险
- fang 物业类型来自房源详情，存在小区内商铺误判风险。