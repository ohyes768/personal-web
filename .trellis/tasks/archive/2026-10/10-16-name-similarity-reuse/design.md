# Design

## 边界

- `name_similarity.py` 是纯函数打分器,本次**不修改**(并行会话所有物,按现状 API 消费:
  `name_similarity(a, b) -> float`、`best_similarity(name, candidate_dict) -> float`、`AUTO_THRESHOLD = 0.92`)。
- 各场景保留自己的决策逻辑,只换/加"怎么算像"。

## 场景 1:法拍

- `auction_fetcher.normalize_auction` 内 `community_name_index(communities).get(name)` 精确命中保持;
- 新增 `fuzzy_community_match(name, communities) -> community | None`:
  对所有小区算 `best_similarity`,取最高分;仅当「最高分唯一(无并列 ≥ 阈值)且 ≥ AUTO_THRESHOLD」返回该小区,
  evidence 追加 `名称相似度 X.XX`。精确命中优先,模糊只在精确 miss 时走。
- `auction_history.associate_records` 的 names.get 分支同样接入(仅 registry 缺失的 legacy 路径)。

## 场景 2:收录审核

- community_auto_review 两处朴素包含(:120 suspicious、:146 同名候选)前叠加
  `name_similarity(成员名, 已有小区名) >= 0.85` 判 suspicious;原子串判定原样保留(只增不减)。
- :132 `exact` 判定不动(merge 分支必须全名精确,风险不对称)。

## 场景 3:高德候选

- `community_enrichment` / `amap_directory` 的匹配与唯一候选绑定逻辑不动;
- 候选进入人工确认(review 状态)时按 `name_similarity(小区名, poi名)` 降序排序,分数随 evidence 展示。
- 实施前先看 amap_directory 并行未提交改动内容,避免覆盖。

## 权衡

- 法拍自动绑阈值复用 0.92:标的名称是小区名的超集,partial_ratio 高分常见,靠"唯一候选"限定挡多义。
- 审核阈值 0.85 偏保守:审核只决定"转人工",多转不出错,少转才出错。
