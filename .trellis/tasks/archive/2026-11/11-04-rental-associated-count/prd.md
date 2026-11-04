# 租金待处理清单补充已采集计数

## Goal

小区数据维护的租金来源待处理清单只显示待处理分组计数（待选择/未找到/暂无在租/查找失败/未查询/已跳过），已关联幸福里来源（采集到租金）的小区被后端排除在清单外，页面上无任何位置显示已采集总数。补充 `associated_count` 让"已采集 N"可见。

## Requirements

- `GET /api/map/rentals/association-tasks` 返回体增加 `associated_count`：当前已关联幸福里租金来源（`active_sources`）的小区数量。
- 前端 `RentalAssociationReview` 在计数按钮排内、"刷新清单"按钮旁显示静态"已采集 N"标签。
- 该标签是纯展示，不是筛选按钮：已关联小区不在清单内，点击无列表可筛（UI 诚实，不做假按钮）。
- 语义边界：人工"已跳过"（decision == skipped）不算已采集——没有来源绑定，仍在待处理清单里。

## Acceptance Criteria

- [ ] 后端测试断言 association-tasks 返回含 `associated_count`，且等于 seeded 数据中已关联来源的小区数（跳过/待选择等不计入）。
- [ ] 前端按钮排显示"已采集 N"，随清单刷新更新；非按钮交互。
- [ ] `python -m pytest tests/ -v`（backend/housing-map）通过。
- [ ] apps/housing-map `pnpm lint` 通过。

## Notes

- 改动面：backend `rental_source_routes.py`（+1 字段）与 tests；frontend `RentalAssociationReview.tsx`（+1 标签）与配套 CSS（如有需要）。
- 轻量任务，PRD-only，无 design.md / implement.md。
