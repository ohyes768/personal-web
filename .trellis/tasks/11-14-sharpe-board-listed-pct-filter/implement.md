# 实施计划：夏普榜单在榜占比筛选 + 精简时间范围

## 0. 上下文

- 任务目录：`.trellis/tasks/11-14-sharpe-board-listed-pct-filter/`
- 需求：`prd.md`；设计：`design.md`
- 规格：`.trellis/spec/backend/fund-select/backend/contracts.md` §23、
  `.trellis/spec/frontend/fund-sharpe-board.md` §10

## 1. 后端

- [x] 1.1 `sharpe_board_service.aggregate_board`：`min_weeks` → `min_listed_pct=60.0`；
      展示筛选改为 `listed_weeks>=1 and listed_weeks*100 >= min_listed_pct*evaluable_weeks`。
- [x] 1.2 `api/sharpe_board.py`：`min_listed_pct: float = Query(60, ge=0, le=100)`。
- [x] 1.3 测试：`TestListedPctFilter`（默认 60、0%=不限、硬门槛、可评周分母）、
      越界 422；旧用例显式传 `min_listed_pct=0` 保持统计/排序断言。

## 2. 前端

- [x] 2.1 `lib/sharpe-board.ts`：`minWeeks` → `minListedPct`（默认 60）、URL 参数
      `min_listed_pct`、去掉 `SharpeRange '1y'` 与 `RANGE_OPTIONS` 里的「近 1 年」。
- [x] 2.2 `SharpeBoardFilters.tsx`：可编辑 0~100 数字输入 + `%` + 分母口径 title。
- [x] 2.3 `page.tsx`：`pageAffecting` / `clearDisplayFilters` 同步改名。
- [x] 2.4 测试：默认 60 / URL 往返 / 越界回落 / 旧 `min_weeks` 落默认 /
      `RANGE_OPTIONS` 恰 3 项、`?range=1y` → `all`。

## 3. 校验

```bash
cd backend/fund-select && .venv/bin/python -m pytest tests/ -q      # 795 passed
cd apps/fund-select
node --experimental-strip-types --test src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts  # 35 passed
npx tsc --noEmit
pnpm build
```

- [x] 3.1 全部通过。
- [ ] 3.2 浏览器/线上验收（部署后）。

## 4. 文档（Phase 3.3）

- [x] 4.1 `contracts.md` 新增 §23 + 更新 §13 旧参数表述 + 两处历史 `min_weeks` 注明为旧口径。
- [x] 4.2 `fund-sharpe-board.md` 新增 §10 + 更新 §1/§7.4 旧表述。

## 5. 提交与部署（Phase 3.4）

- [ ] 5.1 一个功能提交（后端 + 前端 + 测试 + spec + 任务目录）。
- [ ] 5.2 `./scripts/deploy-nas.sh fund-select both` 部署并线上验收。
