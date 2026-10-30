# 设计：幸福里租金配额采样

> **⚠️ 已被取代**：本设计（逐套详情核验 + 详情通过数早停）已由 `10-29-xingfuli-list-api-sampling`
> 的列表 API 抽样方案取代（提交 `20c503a`）。当前代码不再发详情请求、不再有 `detail_failed`
> 补位与 `partial_detail` 状态。当前权威契约见
> `.trellis/spec/backend/housing-map/backend/xingfuli-rentals.md`「列表API抽样契约（2026-10-29）」。
> 下文保留为历史记录。

## 边界

改动集中在四处，其余不动：

| 层 | 文件 | 改动 |
|---|---|---|
| 采集 | `backend/housing-map/src/services/xingfuli_rentals.py` | `crawl()` 配额循环 |
| 编排 | `backend/housing-map/src/services/rental_reference/refresh.py` | `CommunityBatch.quality['sampling']` 元数据 |
| API | `backend/housing-map/src/api/rental_routes.py` | 透传抽样标记（仿 `regional_sample` 的位置） |
| 前端 | `apps/housing-map/src/lib/rental-types.ts` + `components/community/CommunityRentalReference.tsx` | 可选字段 + 一条说明行 |

传输层（xingfuli_transport.py）、统计（statistics.py）、房天下（fang_rentals.py 仅 `SeedRunResult` 复用）不改。`SeedRunResult` 现有字段够用：`detail_success` 即合格样本数，不新增字段。

## crawl() 配额循环设计

现状循环：`for page in range(max_pages)` → 逐行 `_sample` → 整租行即时 `_enrich`（详情）→ 页尾看 `has_more` 决定翻页。

改造（保持结构，插入配额）：

1. 模块常量 `MAX_SAMPLES = 10`。
2. 候选判定在 `_sample` 之后：`sample['rental_mode'] == 'whole'` 且 `'suspected_partition' not in sample['quality_flags']`。非候选行照旧进 `samples`（无详情），不消耗任何请求。
3. 每抓完一个候选详情，检查 `result.detail_success >= MAX_SAMPLES` → 置 `quota_met = True`，跳出本页行循环。
4. 页尾逻辑：
   - `quota_met` → 状态按现有规则收尾（`partial_detail` if detail_failed else `complete`），**不置** `pages_truncated`，不再发分页请求。
   - 未配额满 → 现有翻页逻辑不变（`_updateParams` 取 offset/search_id，分页不推进拒发等）。
   - 翻满 `max_pages` 且未配额满 → `truncated`（现状语义，注：全量模式同样如此，采样只是更常到达配额）。
5. 空列表反查种子详情（`empty_ok` 分支）、`seen` 去重、逐行 `neighborhood_id` 校验、冷却中止全部原样保留。

### 实现注意点

- **状态映射（已确认）**：`ADOPTABLE_STATUSES = frozenset({'complete', 'empty_ok'})`（storage.py:34，test_rental_storage.py:201 锁定，`partial_detail` 不可入库）。采样下的映射：
  - 配额满足 → `complete`（详情失败均已被补位吸收，快照是采样契约下的完整结果，必须入库）；
  - 配额未满足、列表耗尽、无详情失败 → `complete`（小区确实只有这么少）；
  - 配额未满足且有详情失败 → `partial_detail`（无法区分"真没有"和"没抓到"，不发布，保留旧快照）；
  - 翻满 `max_pages` 仍未配额满 → `truncated`（不发布）。
  - **不新增状态值、不改 `ADOPTABLE_STATUSES` 枚举。**
- 配额满足时当前页剩余行仍 `_sample` 入 `samples`（无详情请求），与 R2"样本保留口径"一致。
- `result.deferred` 判定（冷却且首请求即失败）不受影响。

## 数据流与契约

```
crawl(quota=10)
  → SeedRunResult（不变）
  → refresh.py: CommunityBatch.quality['sampling'] = {'sampled': True, 'quota': 10, 'qualified': result.detail_success}
  → 快照存储（quality 已有先例：duplicate_source_ids_skipped）
  → GET 租金 API：snapshot 元数据多一个可选字段 sampling
  → 前端 rental-types.ts 加可选字段；CommunityRentalReference 顶部 notices.append('抽样采集：目标 10 条整租合格样本，非小区全部在租房源。')
```

兼容性：旧快照与房天下快照无 `sampling` 字段 → API 字段可选、前端条件渲染，无迁移。

## 取舍记录

- **补位式配额 vs 候选上限**（用户拍板 Q2）：请求预算可变，换样本量保证；病态失败由冷却熔断兜底。
- **不按面积筛**（用户拍板 Q1）：保护统计分组口径。
- **所有行入 samples、只有详情受配额**：保持"已排除样本"明细完整，比"只留候选"改动小、信息不丢。
- **不加开关**（用户拍板 Q3）：抽样在 ≤10 整租小区与全量等价，配置项无服务对象。

## 回滚

改动无数据迁移：回滚代码即恢复全量采集；已产生的抽样快照仍可读（缺 sampling 字段时前端不出说明行）。
