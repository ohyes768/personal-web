# 唯一候选自动绑定高德 POI

## Goal

放宽 `position_one` 的自动匹配规则（用户拍板）：**查询未截断且候选唯一时直接 matched**，
不再要求名字精确命中与地址精确相等；多候选才进人工确认。

## Background

2026-10-16 生产库统计（155 小区）：review 124，其中单一候选 113（精确命中 93、
包含命中 20）、多候选 4、无候选（截断）7。现规则因"地址字符串不等"把 93 个
明明唯一的候选挡在人工确认里，违背用户零点击偏好。

## Requirements

- R1 自动匹配条件从 `count <= 25 and len(candidates) == 1 and len(exact) == 1
  and candidates[0]['source_id'] in exact_ids` 收敛为
  **`count <= 25 and len(candidates) == 1`**：
  - 名字包含命中（宽松候选）在唯一时也允许自动 matched（如 世茂之西湖 → 御涛轩）。
  - 地址不一致在唯一时不再阻断匹配。
  - `count > 25`（截断）时唯一候选仍进 review——截断下"唯一"不可信。
- R2 多候选 → review、无候选走别名重查后仍无 → not_found，行为不变。
- R3 不变式：previous-state 保护、`_publish` 快照比对、别名重查触发条件
  （无候选且未截断）、预算/暂停/取消全部不变。matched 仍只在没有已有
  地图位置时写坐标，人工确认才覆盖坐标。
- R4 同步更新 .trellis/spec/backend/housing-map/backend/directory-position.md
  第 3 节自动匹配契约与第 6 节测试清单。

## Acceptance Criteria

backend/housing-map/tests/test_position_status.py（改既有断言而非另起炉灶）：

- [ ] 单一宽松候选（POI 名超集，地址不同）→ matched，不再 review。
- [ ] 单一精确候选、地址不一致 → matched。
- [ ] 多候选 → review（含"精确+宽松并存"用例）。
- [ ] 截断（count > 25）时唯一候选 → review，文案不变。
- [ ] 别名重查命中唯一候选 → matched（沿用现有用例调整断言）。
- [ ] 单一候选 matched 后写入的 selected 为该候选，previous/manual 保护用例全过。
- [ ] 全量 pytest 通过。

## Notes

- 部署后存量迁移（人工执行，不在代码范围）：把"单一候选的 review"重置为
  pending，重跑批量即可自动绑定；多候选/截断的 review 与 not_found 不动。
- `_name_matches` 保留（候选过滤仍按名字集合），仅匹配决策放宽；exact_ids
  若不再被决策使用可随之简化。
