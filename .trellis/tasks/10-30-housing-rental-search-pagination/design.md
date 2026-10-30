# 技术设计：搜索分页续查与失败状态区分

## 根因（2026-10-30 线上 07:57~07:58 批次复盘）

1. `XingfuliDiscovery.search` 固定 `offset=0, count=20`；满页或 `total > len(items)` → `search_complete=False`。
2. `DiscoveryCheckpoint` 刻意不复用 `complete=False` 的搜索步（防"死胡同回放"），于是继续匹配每轮都真实重查第一页、得到同样的不完整结果，永远推进不了。
3. `ProbeService._search` 把所有"没查全"信号（满页、community_info 失败、候选截断）聚合进一个 `incomplete`，无候选时统一 `upstream_failed` → 页面显示"查询失败"，实际是"还有页没查"。
4. 批次把 `deferred` stage 记为 outcome `'failed'` → 批次统计"查询失败 N"混入了未查完的小区。

## 设计决策

### 1. 搜索分页协议（`xingfuli_discovery.py`）

- `search(name, channel, offset=0)`，新增常量 `SEARCH_PAGE_SIZE = 20`；URL 透传 offset（URL 白名单本就允许 `offset` 参数，无需改 `validate_discovery_url`）。
- `search_complete` 语义不变：**本页响应**是否结束该（名字, 通道）的结果列表。
- 不动 `same_neighborhood_rent`（offset 钉死 0），匹配任务不采集租金。

### 2. checkpoint v3（`discovery_checkpoint.py`）

- `VERSION` 2 → 3：搜索步骤键从 `['search', name, channel]` 变为 `['search', name, channel, offset]`，旧 v2 缓存整体作废。TTL 仅 24h，无迁移价值。
- **缓存复用规则翻转**：删除"`complete=False` 搜索步不复用"的条件。分页后，不完整页不再是死胡同，而是"此页已读过 + 后面可能还有页"的进度事实：复用它（零请求），然后真实请求下一 offset。每步仍记录自己的 `complete`，回放时设置 `self.search_complete`。
- 其余不变：TTL、身份指纹、live 请求前检查预算/取消、失败与冷却不落缓存。

### 3. 探查分页循环（`probe.py` `_search`）

每（名字, 通道）顺序翻页：offset 0 → 20 → …，直到以下之一：

- `search_complete=True`：通道正常查完（trusted）；
- `DiscoveryBudgetExhausted`：预算尽 → 异常路径 `deferred`（未查完，进度已缓存）；
- 页请求 `ValueError`（非冷却）：记录 page_error，该通道停止翻页，继续下一通道；冷却直接 `cooling_down` 返回（现状不变）；
- **重复页保护**：offset>0 的页未贡献新 `neighborhood_id` 且 `complete=False` → 该通道标记 degraded，停止翻页（平台忽略 offset 或 total 说谎，无法证明唯一性）；
- 候选达 `MAX_CANDIDATES`：truncated（现状语义保留）。

**信号重组**（替代单一 `incomplete`）：

| 信号 | 无候选终态 | 有候选 |
|---|---|---|
| page_errors | `upstream_failed`（请求失败，可重试），message 保留具体原因 | 走 needs_selection，不得自动绑定 |
| 预算尽 | `deferred`（未查完，可继续） | 不得自动绑定 |
| degraded / truncated | —（degraded 必有候选） | needs_selection |
| 全通道 complete 且无候选 | `homepage_not_found`（未找到） | 允许早停 / 单强候选自动绑定 |

**自动绑定门槛**：仅当所有已查通道都正常 complete 结束（无 page_errors / degraded / truncated，预算异常根本走不到绑定）才允许早停与唯一强候选自动绑定。分页未完时可见的唯一候选只是"当前页唯一"，不是完整唯一证据。

### 4. 状态语义（不新增 stage）

复用现有 stage，含义收紧：

- `deferred` = 未查完，可继续（本轮预算用尽，已查页已缓存）
- `upstream_failed` = 请求失败，可重试（仅真实请求错误）
- `homepage_not_found` = 已查完所有页且无相关候选
- deferred 的 message 改为"幸福里搜索未查完：本轮请求额度已用完，可继续匹配"

### 5. 批次统计（`matching.py`）

- stage → outcome 映射增加 `'deferred': 'deferred'`（不再落入 `'failed'`）。
- `association` 新增 `incomplete` 键 = outcomes 中 `'deferred'` 的数量；`deferred` 键保持 = `len(remaining)`（本轮未轮到的小区）。
- `_targets('incremental')` 无需改：completed 集合不含 `deferred`，未查完小区下一轮自动重新入队。
- 旧 job json 里的 `'failed'` 记录（部分实为未查完）：不迁移，incremental 重查后按新语义归位。

### 6. 前端

- `rental-probe.ts`：`deferred` 文案 → `搜索未查完，可继续`。
- `RentalAssociationReview.tsx`：`search_deferred` 详细文案 → `未查完或未查询，可继续匹配`。
- `DirectoryFlowWorkspace.tsx`：批次统计行加 `未查完 {incomplete}`，association 内联类型加 `incomplete?: number`（渲染容错缺失）。

### 7. 预算限额

不新增独立页数上限：现有单小区轮次预算（批次与手动均 12 请求）即硬上限，每页恰 1 请求；重复页保护兜底 `total` 说谎的无限翻页。缓存回放不计预算，因此续跑永远从第一个未缓存页继续。

## 兼容与回滚

- 缓存：v3 代码忽略 v2；回滚后 v2 代码同样忽略 v3（version 不匹配）——双向安全重查，无脏读。
- 旧 `upstream_failed` 状态记录：下次探查按新语义重新归位，无 schema 迁移。
- 回滚 = revert 提交。

## 风险

- 平台 `total` 不可靠（PRD 已点名）：complete 判据保留 `len<20 and not total>len`，重复页保护兜底。
- 缓存复用翻转后若翻页逻辑有 bug，可能复用错误进度：VERSION 隔离 + 专项测试覆盖（断点续跑、失败重试、重复页）。
- `test_matching_speed.py` 的"不完整搜索步不缓存复用"契约被本设计有意推翻，spec 同步改写。
