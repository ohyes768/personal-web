# Journal - jackson.tang (Part 1)

> AI development session journal
> Started: 2026-08-27

---



## Session 1: 宏观定时任务与独立管理页面

**Date**: 2026-08-27
**Task**: 宏观定时任务与独立管理页面
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

宏观后端移植 dividend scheduler 架构:新增 src/scheduler 包(run_group 组执行器,顺序 self-call 16 个 update 端点,单源失败不中断,聚合 success/partial/failed/skipped,历史含数据源级 items 明细),scheduler.json 预设 A 股组(工作日16:10+交易日校验)与全球组(工作日07:30),4 个管理 API,25 个单测;前端新增 /macro/scheduler 独立管理页(启停/立即执行/双层历史明细)+ 主页齿轮悬浮入口;浏览器端到端点验通过(真实触发 36s partial 5/6 成功,fund-flow 外部源断连属数据源问题);契约沉淀至 spec/backend/global-macro-fin/backend/scheduler.md

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `20a6b2e` | (see git log) |
| `fc94345` | (see git log) |
| `b245872` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 宏观页数据 Tab 写入 UX 统一

**Date**: 2026-08-29
**Task**: 宏观页数据 Tab 写入 UX 统一
**Package**: backend/global-macro-fin
**Branch**: `master`

### Summary

六个数据 Tab 统一初始化/更新/置灰；成交额历史改到 /fetch/volume-turnover/history；市场情绪三个增量串行，避开全局更新锁。信号首页与对比保持只读。

### Main Changes

- 六个数据 Tab（中美利差/汇率、流动性/风险、利率利差、商品、股指、市场情绪）统一 InitButton + RefreshButton：文案「初始化历史数据」/「更新数据」，成功后 onSuccess 刷图，各用独立 storageKey。
- 信号首页与对比保持只读，不加写数按钮。
- 成交额+换手率历史规范为 POST /api/fetch/volume-turnover/history；删除旧 /update/volume-turnover/history，不留别名。
- 市场情绪更新串行打 volume → turnover → margin，避开 routes.py 全局 _is_updating 锁；不抄流动性 Tab 的 Promise.all。
- 融资余额 history 与流动性并发锁修复不在本任务范围。


### Git Commits

| Hash | Message |
|------|---------|
| `26538b4` | (see git log) |
| `c394523` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 融资余额历史回补接口

**Date**: 2026-08-29
**Task**: 融资余额历史回补接口
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

新增 POST /fetch/margin/history，akshare 沪深全表按日期 outer join 回补 margin.csv；市场情绪初始化串行 volume-turnover → margin → fund-flow history。pytest tests/test_margin.py 12 passed。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `ce6c8cc` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: QDII/互认基金跳过业绩基准合成

**Date**: 2026-09-03
**Task**: QDII/互认基金跳过业绩基准合成
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

股票宇宙刷新时 QDII/互认基金不再合成业绩基准 TRI（公式多无免费源，fallback 中证800口径失真），直接写 tri=NULL/source=skipped:qdii，界面 IR/α/γ/α-IR/超额3y 显示 -，夏普与净值业绩不受影响；判定口径同 exclude_qdii；funds_stock.yaml 移除 968157；新增 5 用例。遗留：sh000922/000908 停更换源（中证红利→中证800 fallback 精度问题）待另立任务。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `a22fd17` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

## 2026-09-04 | 09-04-stock-fund-sharpe-filter

### Summary

股票 tab 筛选接入已有夏普指标（fund_risk_metrics.sharpe，近 3 年）：/stock/screen 新增 min_sharpe，NULL 指标一并排除；前端股票 tab 侧栏加夏普输入项默认 0.8（FilterPanel 改 dimensions prop 可配置，债基保持四维隔离）。实测完整默认组合 6 只、单夏普条件 53 只、移除 chip 恢复 22 只。

### Main Changes

- backend: filter_service._screen 尾参 min_sharpe + where；routes.stock_screen 加 Query(ge=-10, le=10)
- frontend: types/useFilters/api/hooks 贯通 min_sharpe；FilterSidebar 导出 STOCK_DIMENSIONS；FilterSheet 透传
- tests: 新增 min_sharpe 筛选/NULL 不受影响 2 用例（TDD，先 RED 后 GREEN）
- spec: contracts.md 关键语义区补 min_sharpe 契约

### Git Commits

| Hash | Message |
|------|---------|
| `877d18b` | feat(fund-select): 股票 tab 筛选接入夏普指标（默认 ≥0.8） |

### Testing

- 后端 pytest 全量 162 passed；ruff 通过
- 前端 tsc --noEmit 通过；build 编译成功（standalone symlink EPERM 为既有 Windows 环境问题，stash 验证无改动同样报错）
- Playwright 实测：侧栏夏普输入 0.8 / chip「夏普 ≥ 0.8」/ 共 6 只；移除 chip → 22 只；债基 tab 4 项无夏普、18 只正常

### Status

[OK] **Completed**

### Next Steps

- 未 push（等用户确认）；pnpm lint 未跑通系该 app 未初始化 ESLint 配置（既有）
