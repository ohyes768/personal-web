# 技术设计：住宅目录高德分类复核与冲突审核

## 1. 边界与不变量
- 改动集中在 housing-map 目录流（directory-flow）内部；定位（position）、租金、法拍不新增耦合，只通过既有 `eligibility` 单一资格口受益。
- 高德分类证据的地位：**可制造待审核、可支撑人工确认、永不自动收录/排除**。`classify_sources`（跨源用途分类）继续忽略 amap 来源，本机制不走它。
- 收录仍由 `directory_policy.eligibility` 纯函数一票裁决；人工确认只覆写「用途类型」这一道门，区域/地址/挂牌等门槛照常执行。
- 存储全部附加（payload JSON），无 schema 迁移、无启动期网络调用；无证据时行为与现状逐项一致。

## 2. 数据模型
### 2.1 复核证据：master payload 附加 `use_review`
与 `amap_position` 同款模式，身份指纹失效：
```
use_review = {
  identity: <与 amap_position 相同口径的身份指纹>,
  rule_version: 'use-review-v1',
  state: 'checked' | 'not_found' | 'error' | 'uncertain',
  category: 'residential' | 'mixed' | 'non_residential' | None,   # state=checked 时有效
  checked_at, error,
  evidence: {poi_id, name, typecode, type_text, address, longitude, latitude,
             district, matched_by: 'exact'|'alias'|'loose'}
}
```
- `uncertain` = 同区名称匹配候选 ≥2 且分类不一致，或多候选无法唯一归类；不作为任何方向的证据。
- 身份指纹变化 → 旧证据失效（投影为无证据）；规则版本升级 → 需重查。不做时间 TTL（分类稳定，省配额）。
- 多候选但分类一致：evidence 记代表 POI，另存 `candidates_count`。

### 2.2 人工决定：复用 `community_admission`
新增受控路径（区别于被目录模式禁止的旧 `admit`）：
```
{state: 'admitted'|'excluded', decision_kind: 'manual', use_rule: 'use-review-v1',
 property_type, use_evidence: [{source: 'kerui'|'fang'|'amap'|'other', url, note}],
 reason, revision, decided_at, ...}
```
- 复用既有 revision 乐观锁、事件审计（新事件 `admission_use_confirm`，含 previous）与人工权威语义（不被自动恢复）。
- **复审触发**：`decided_at` 之后出现新的相反证据（TMSF 类型/冲突标记更新，或 `use_review.checked_at > decided_at` 且方向相反）→ eligibility 投影回待审核并在排除页提示「有新证据待复审」；已存决定不删除、不覆盖。

## 3. 纯函数层：分类映射与冲突矩阵
新模块 `src/services/use_review_policy.py`（纯函数，先行测试）：
- `amap_category(typecode)`：`120300|120301|120302|120303|120304`（任一段）→ residential；`120203` → mixed；其他非空 → non_residential；空 → None。复用 `normalize_poi` 的 `|` 分段口径。
- `select_evidence(pois, community)`：复用 directory-position 的名称拉平/别名/包含匹配与同区边界规则，只认名称匹配候选；0 个 → not_found，1 个或多候选分类一致 → 该分类，候选分类冲突 → uncertain。**匹配规则直接引用/抽取 position 的现有实现，不另写一套**（防止两套拉平逻辑漂移）。
- `compare(tmsf_types, amap_category)` → `agree_residential | agree_non_residential | conflict | uncertain | pending_retry`，映射 PRD 决策矩阵；`pending_retry`（无证据/not_found/error/uncertain 身份）时 TMSF 原判定不变。

## 4. eligibility 变更（`directory_policy.eligibility`）
类型门槛段（现 36-50 行）改为：
1. 人工用途决定存在且无更新相反证据 → 人定优先（residential → 按 `admission.property_type` 通过类型门；non_residential → 排除，理由用人工 reason）。
2. 否则取 `use_review` 投影（身份指纹匹配 + rule_version 匹配）与 TMSF 类型跑矩阵：
   - `conflict` → `use_conflict`（incomplete，「用途分类冲突待审核」）
   - `uncertain` → `use_uncertain`（incomplete，「用途待确认」）
   - `agree_*` / `pending_retry` → 维持现行结果与 reason 文案。
- 新增 qualification 码只增不改；`community_views` 无需新逻辑（excluded + incomplete 的展示模式既有）。

## 5. 查询与批量任务（`src/services/directory_use_review.py`）
- `AmapClient.search_name` 增加 `types` 参数（默认现值，传 `None` 表示不限类型）——最小改动，定位调用方不受影响。
- `review_one(cid, *, client, cancelled, force)`：不限类型搜索 → `select_evidence` → 写 `use_review` payload；网络在事务外，写入事务内重核身份指纹与快照；取消后不写（与 `position_one` 同构）。
- `UseReviewJob`：持久任务（`/use-reviews` GET/POST/DELETE），与 PositionJob 同构——快照全部未删除未合并 master（含 admitted 与 excluded，矩阵第 3 行只能从已收录侧发现）、跳过已有同指纹同规则版本证据的目标、256 请求预算、2s 间隔、取消/中断续跑、按结果（updated/conflict/not_found/error/skipped）而非失败报告、空跑无需 key。
- 配额口径：任务报告请求数；全目录一次性跑一遍在个人 5000/月配额内（目录规模数百级）。

## 6. API（`directory_workflow_routes`，外部前缀 `/api/map/directory/workflow`）
- `POST /catalog/{cid}/use-review`：单小区显式重查（同 position/query 形态），返回当前投影 + errors。
- `POST /catalog/{cid}/use-review/confirm`：`{revision, decision: 'residential'|'non_residential', property_type?, use_evidence: [{source,url,note}]（非空，url 必填）, reason（non_residential 必填）}` → 写入 2.2 决定。仅目录模式可用；删除/合并目标 409。
- `GET /catalog?use=conflict|uncertain|pending_retry|agree|none`：复核视角过滤，分页前生效（同 position 过滤）。
- catalog 行新增 `use_review` 投影：`{state, category, result, checked_at, poi 摘要, human: {decision, decided_at} | null, re_review: bool}`。
- 错误矩阵沿用：422 非法输入 / 409 未激活、revision 过期、未知目标 / 503 存储。

## 7. 兼容与回滚
- 无证据路径逐字节等价（AC3 用存量目录流测试 + 投影快照对比锁死）。
- 回滚 = 代码回退；payload 附加字段被忽略，无数据破坏。
- 生产启用路径：部署 → 用户显式发起批量复核（或单小区重查）→ 审阅冲突队列 → 逐个 confirm。不做部署自动跑批。

## 8. 权衡记录
| 决策 | 选择 | 备选与否决理由 |
|---|---|---|
| 证据来源 | 独立不限类型查询 | 复用定位关联 POI：定位搜索限定住宅白名单，结构上发现不了「高德非住宅」，且 `amap_position` 不存 typecode |
| 人工决定存放 | `community_admission` 表 | master payload：会造出第二套 revision/锁机制，与 admission 权威语义冲突 |
| 批量范围 | 全目录 | 只跑排除项：矩阵「住宅×非住宅」冲突只能从已收录侧发现，目录规模对配额无压力 |
| 缓存失效 | 指纹/规则版本，无 TTL | 时间 TTL：分类稳定，TTL 只浪费配额 |
| 高德非住宅判定 | 仅同区+名称匹配 POI | 放宽到任意命中：同名异地/附属设施会误判 |

## 9. 风险
- **共享工作区**：xingfuli 租金任务（in_progress，未提交）已改 `community_registry.py` 等文件；本任务实施前须 `git diff HEAD` 核对并基于其上开发，提交范围严格限本任务文件。
- eligibility 是全站资格单口，改动波及租金/法拍/地图集合——AC3 等价性测试是硬闸门。
- 高德配额与风控：批量任务必须可取消、有预算上限；配额不足时按 not_found→pending_retry 处理，绝不臆断。
