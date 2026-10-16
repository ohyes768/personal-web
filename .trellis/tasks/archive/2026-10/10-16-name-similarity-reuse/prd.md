# PRD:名称相似度流水线复用

## 背景

`src/services/name_similarity.py`(并行会话产出,未提交)实现了中文名相似度打分流水线:
归一化 → 专名/通名拆分 → 拼音兜底 → 三算法取最高分(fuzz.ratio / JaroWinkler / partial_ratio),
分期冲突(一期 vs 二期)短路 0 分。已接入租金来源场景(auto_associate 唯一候选自动绑 + 待选择按分排序)。

## 需求

将同一打分器复用到另外三个"判断两个名字是否指同一家"的场景:

1. **法拍→小区关联**(auction_fetcher / auction_history)
   现状仅精确名称匹配;改为:精确匹配保留,失败后唯一候选且 `best_similarity ≥ 0.92`(AUTO_THRESHOLD)自动关联,evidence 标注分数;其余维持人工。
2. **小区收录自动审核**(community_auto_review)
   现状用朴素子串包含判 suspicious;改为:原子串判定保留,叠加 `name_similarity ≥ 0.85` 也判 suspicious(只增不减,保守门)。
3. **高德定位候选**(community_enrichment / amap 候选流)
   绑定逻辑不动(用户已拍板:唯一候选即绑定);仅在候选进入人工确认时按名称分数排序展示,帮助快速核对。

## 约束

- 打分统一走 name_similarity 模块;决策阈值留在各场景(租金 0.92 / 审核 0.85 / 定位仅排序)。
- 前提:name_similarity.py + 测试 + community_registry/association 的既有接线一并纳入本次提交(先跑测试确认)。
- 不改 data_loader 的 POI 去重(一次性治理,无收益)。

## 验收标准

- housing-map 后端全量 pytest 通过;新增各场景单测覆盖:精确命中、唯一高分自动、多候选不自动、分期冲突 0 分。
- 高德场景:绑定行为与现状完全一致(仅排序/展示变化),现有测试不回归。
- 前端 build/lint 通过(若涉及候选展示)。
