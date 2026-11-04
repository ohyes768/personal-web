# 看板移除租金筛选器与租金三列

## Goal

延续 11-03「移除小区租金与收益页签」的租金退役收尾：数据看板上残留的租金筛选器（面积段/房型）与租金三列整套移除，与已退役的详情页租金页签保持一致，面向购房者的看板不再出现租金信息。

## Requirements

1. 移除看板筛选栏的 `RentalScopeSelect`（租金面积段 + 租金房型两个下拉）与「租金数据暂不可用」提示。
2. 移除看板表格租金三列（租金单价 / 参考年化收益率 / 租金样本数）的表头与单元格，及对应排序键 `rent_unit` / `rent_yield` / `rent_samples`。
3. 移除 `rentalScope` state、`useRentalSummary` 调用、口径说明中的租金句子。
4. 删除随看板死亡的孤儿文件/导出：
   - `src/components/dashboard/RentalDashboardWidgets.tsx`（整文件）
   - `src/lib/use-rental-summary.ts`（整文件，唯一消费方是看板）
   - `src/lib/rental-dashboard.ts` 中仅看板使用的导出：`rentalSortValue` / `sortRowsByRentalKey` / `isRentalSortKey` / `indexSummaries` / `formatUnitRentCell` / `formatYieldCell` / `formatSampleCountCell`
   - `src/lib/rental-types.ts` 中仅 summary 链路使用的 `buildRentalSummaryPath` / `RentalSummaryData` / `RentalSummaryEntry`（`RentalAreaBand` / `RentalBedroomsFilter` 被详情链路共用，保留）
5. 更新 `tests/rental-dashboard.test.cjs`：裁剪被删函数与组件的测试块，保留 refresh 诊断测试。

## 明确不动（范围外）

- 维护页签租金采集链路：`use-rental-data.ts`、`DirectoryFlowWorkspace.tsx`、`rentalRefreshDiagnostics`、`RENTAL_DATA_CHANGED` 事件。
- 详情概览「租售比 / 年化毛收益率」：`CommunityRentalMetrics.tsx`（移除页签后特意保留的产品决策）。
- 后端 `/api/rentals/summary` 端点（`backend/housing-map/src/api/rental_routes.py`）：前端看板删除后暂无消费方，但删除涉及后端契约与统计服务，另行处理。
- `rentalRefreshProgressText` / `rentalRefreshTerminalNote`：src 中已无消费方（先前重构残留），本次不动。
- `CommunityRentalReference.tsx`：11-03 移除页签后的孤儿组件（src 无引用），本次不动，汇报时提示用户。

## Acceptance Criteria

- [x] `pnpm lint` 通过（apps/housing-map）
- [x] `node --test tests/*.test.cjs` 全部通过（195/195）
- [x] `npx tsc --noEmit` 通过（等价替代 `pnpm build` 的类型验证：另一会话 dev server 独占 `.next`，跑 build 会清其缓存，故不在本机跑 build）
- [x] 看板页面不再出现「租金面积段 / 租金房型 / 租金单价 / 参考年化收益率 / 租金样本数」任何 UI 与排序
- [x] `grep` 确认 `apps/housing-map/src` 中无 `RentalScopeSelect` / `RentalSummaryCells` / `useRentalSummary` / `rent_unit` / `rent_yield` / `rent_samples` / `buildRentalSummaryPath` / `RentalSummaryEntry` 残留
