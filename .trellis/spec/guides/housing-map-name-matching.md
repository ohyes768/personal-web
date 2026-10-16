# Housing-Map 名称相似度契约

> 判断"两个名字是否指同一家小区"时,统一走 `src/services/name_similarity.py`,不要在场景里自写字符串比对。

## 打分器(name_similarity.py,纯函数,零状态)

- `name_similarity(a, b) -> float`(0~1):归一化 → 通名剥离(GENERIC_NAMES 词表,数字保留)→
  取 `fuzz.ratio` / `JaroWinkler` / `partial_ratio`(双方 ≥3 字才启用)最高分;无调拼音兜底。
- **分期冲突短路**:双方都带期号(`一期`/`二期`…)且不同 → 直接 0 分。字面像但不是一家的典型。
- `best_similarity(name, candidate)` → 对候选的 community_name/alias/aliases 取最高分(候选字段名固定)。
- `AUTO_THRESHOLD = 0.92`:唯一候选自动绑定的门槛。

## 各场景决策阈值(打分统一,决策分场景)

| 场景 | 位置 | 规则 |
|---|---|---|
| 租金来源 | community_registry.auto_associate | 精确名唯一 > 唯一候选 ≥0.92 自动绑;其余人工 |
| 法拍→小区 | auction_fetcher.fuzzy_community_match | 精确索引 miss 后,唯一候选 ≥0.92 自动关联 |
| 收录审核 | community_auto_review(REVIEW_SIMILARITY=0.85) | 朴素子串判定**保留**,叠加 ≥0.85 也转人工(只增不减) |
| 高德定位 | directory_position(position_one) | 绑定逻辑不变;review 多候选按分数降序,分数入 `name_similarity` 字段 |

## 已知边界(勿试图用算法解决)

- 推广名 ≠ 备案名:字面零重叠,只能靠 aliases 或人工;
- 分期:marker 冲突短路保护,但**单边无期号时**(如标的"白金海岸3幢" vs 候选"白金海岸一期")分数仍高,
  靠"唯一候选"限定 + 人工兜底;
- `_name_matches`(directory_position)有自己的 `_flat_name`/`_GENERIC_SUFFIX` 词表,与 name_similarity
  词表**不同步**,因此高德候选分数可能并非全部 1.0;两词表合并前不要删任一侧。

## 测试隔离

涉及 legacy 名称匹配的测试(auction_history 等)必须把 `MAPPING_PATH` patch 到 tmp——
真实 `data/community_registry.sqlite3` 存在时名称匹配分支会被跳过。
