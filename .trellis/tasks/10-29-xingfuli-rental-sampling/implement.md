# 执行计划

## 顺序清单

1. **测试先行（RED）**：`tests/test_xingfuli_rentals.py` 新增用例：
   - `test_quota_stops_paging`：>10 条整租，第 10 条合格后无分页请求，`status='complete'`、`pages_truncated=False`
   - `test_quota_skips_partition_suspects`：疑似隔断行不做详情、不算配额
   - `test_quota_backfills_after_detail_failure`：第 2 条候选详情失败 → 继续抓第 11 条整租补位
   - `test_small_community_unchanged`：≤10 条整租行为与全量一致
   - 既有防线用例（混入他区/末页重复/空列表反查/冷却）确保仍绿
2. **实现 crawl 配额**：`xingfuli_rentals.py` 加 `MAX_SAMPLES = 10` + 循环配额逻辑（GREEN）
3. **状态映射**：`ADOPTABLE_STATUSES = {'complete','empty_ok'}` 已确认（storage.py:34）。实现 design.md 的四条映射，重点：配额满足 → `complete`（即使有 detail_failed）；配额未满 + 有失败 → `partial_detail` 不入库；不改枚举
4. **编排元数据**：refresh.py `CommunityBatch.quality['sampling']` 三个字段；确认快照存储无 schema 排斥（quality 为自由 dict）
5. **API 透传**：rental_routes.py 快照 → 响应加可选 `sampling` 字段；`tests/test_rental_api.py` 补断言
6. **前端**：rental-types.ts 可选字段 + CommunityRentalReference 说明行（条件渲染，无字段不显示）
7. **全量验证**（见下）+ 浏览器目检面板说明行

## 验证命令

```sh
cd backend/housing-map && python -m pytest tests/ -q
cd apps/housing-map && pnpm lint && pnpm build
```

## 风险与回滚点

- 步骤 2 是核心风险：改动 crawl 循环，若防线用例变红立即回退该文件。
- 步骤 3 的状态语义若与预期不符，先回 PRD 补验收再动代码（Plan 回滚）。
- 每步独立提交可回退；无数据迁移，回滚代码即恢复全量。

## task.py start 前检查

- [ ] prd.md / design.md / implement.md 齐备且用户已评审
- [ ] implement.jsonl / check.jsonl 有真实条目（非 _example 种子）
