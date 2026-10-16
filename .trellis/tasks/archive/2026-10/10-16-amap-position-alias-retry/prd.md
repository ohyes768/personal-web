# 高德位置补全支持别名重查与名称包含匹配

## Goal

降低 `position_one`（backend/housing-map/src/services/directory_position.py）的 not_found 误报：
主名在高德查不到可靠候选时，用别名重查；POI 名与小区名互为包含时纳入 review 候选。
自动定位规则不变，仍只进 review 不自动选择。

## Background（2026-10-16 实测，滨江/杭州，types=120300）

| 小区 | 高德实际返回 | 现状结局 | 本任务效果 |
|------|-------------|---------|-----------|
| 世茂之西湖 | POI「世茂之西湖御涛轩」（滨江区） | not_found（名称精确相等匹配失败） | 包含匹配 → review 候选 |
| 世茂之西湖茂御居 | POI「茂御居」（滨江区，地址江南大道） | not_found（主名搜索无精确候选） | 别名重查 → 候选 |
| 世茂智慧之门 | 住宅类无 POI（只有写字楼"智慧之门中心"） | not_found | 无改善，维持人工定位 |

现状代码：匹配集合已含别名（directory_position.py:98 `names`），但搜索关键词只用主名
（directory_position.py:105）。匹配只接受归一化后**精确相等**。

## Requirements

### R1 别名重查（not_found 时触发）

- 触发条件：主名查询后无任何候选且 `count <= 25`（即现有 not_found 分支）。
  review 状态（已有候选）与 count > 25（疑似截断）不重查。
- 别名先归一化去重（`normalized`），排除与主名归一化后相同的别名；每个小区最多重查 3 个别名，
  超出的忽略（保证单小区上游请求 ≤ 4，budget 语义见 R3）。
- 每个别名调用与主名相同的 `search_name(alias, district)`，结果走相同的
  `normalize_poi` + 名称过滤 + 去重；命中候选即停止重查后续别名。
- 重查后仍无候选 → 维持 not_found；得到候选 → 按现有规则判定 matched/review。

### R2 名称包含匹配（review-only）

- 在名称过滤中，除精确相等外，POI 名（归一化后）与小区名集合中的名字互为
  子串（任一方向）也算名称命中，记为"宽松候选"。
- 防噪音：参与包含匹配的一方的归一化长度必须 ≥ 3（过滤"西湖"这类短名大面积误命中）。
- 自动匹配（matched）条件收紧为：唯一候选、且该候选为**精确相等**命中（非宽松）、
  且地址精确相等、且来源查询 `count <= 25`。存在宽松候选时一律 review，
  候选列表 = 精确候选 + 宽松候选（按 source_id 去重）。
- 包含匹配对主名查询与别名重查的结果同样生效。

### R3 不变式（不得破坏）

- 自动匹配规则其余部分不变：唯一候选 + `qualified_address` 精确相等 + 结果未截断。
- 已有 matched/manual 结果的跳过逻辑（`keep_position`、previous 保护）不变。
- 别名重查请求不单独计入 job 的 `requests` 计数（预算仍按小区计，`budget=256`），
  以 R1 的 3 次上限保证实际上游请求有界；此取舍需写入 spec。
- 状态机、`_publish` 快照比对、取消/中断行为不变。
- 无 schema 变更；前端无需改动（候选渲染与 confirm 走既有通道）。

## Acceptance Criteria

测试文件：backend/housing-map/tests/test_position_status.py（遵循现有 fake client 模式）

- [ ] 主名无精确候选、别名精确命中（如"茂御居"）→ 别名重查产生候选；
      唯一且地址精确相等时自动 matched，否则 review。
- [ ] 别名重查后仍无候选 → not_found，错误文案不变。
- [ ] POI 名为小区名超集（"世茂之西湖御涛轩" ⊃ "世茂之西湖"）→ 宽松候选进入
      review，绝不自动 matched（即使唯一且地址相等）。
- [ ] 精确候选与宽松候选并存 → review，两者都出现在 candidates。
- [ ] 短名（归一化长度 < 3）不参与包含匹配。
- [ ] 别名与主名归一化相同 → 不发起重复查询；有效别名 > 3 个 → 只重查前 3 个
      （fake client 记录调用次数验证）。
- [ ] 主名有精确候选（review/matched 路径）→ 不发起别名查询。
- [ ] count > 25 且无候选 → 维持现有 review 文案，不重查。
- [ ] 全量 `python -m pytest tests/ -v` 通过（Windows 环境注意 .trellis/spec/backend/testing-environment.md 约束）。

## Notes

- 完成后需更新 .trellis/spec/backend/housing-map/backend/directory-position.md
  第 3 节 "Lookup keeps exact full-name/alias..."：补充别名重查触发条件、
  3 别名上限、宽松候选 review-only 规则与预算取舍。
- 参考依据：`normalized()` = NFKC + 去空白 + casefold（community_registry.py:15），
  包含匹配即归一化后的子串判断。
