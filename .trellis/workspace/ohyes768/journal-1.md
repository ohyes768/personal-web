# Journal - ohyes768 (Part 1)

> AI development session journal
> Started: 2026-08-04

---



## Session 1: 行情价与M120解耦修复挡位监控空窗

**Date**: 2026-08-10
**Task**: 行情价与M120解耦修复挡位监控空窗
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

修复挡位监控 tab 在 M120 数据缺失时整页空白的 bug。根因：后端 m120_service.read_m120_with_deviation 以 M120 CSV 为主表 join 实时价格（line 474 for m120_df），M120 CSV 缺失时 return {}（line 421-423）使现价被一起埋没；前端 useTechnicalData 只走 /api/dividend/m120，挡位监控 currentPrice=null 导致所有 AlertLevelBar return null，tab 计数>0 但内容空白（page.tsx 1069-1071）。修复：新增 read_prices_only() + GET /api/dividend/prices 独立现价通路（不以 M120 为主表）；前端新增 useRealtimePrices hook，挡位监控段改读 alertPriceMap 而非 technicalData。改动：子模块 4cad20a（m120_service 抽 _read_price_csv + read_prices_only、routes 抽 _compute_yield_ttm helper + 新增 /prices、models 加 PriceItem/PriceListResponse、tests +5 用例）+ 主仓库 7531772（前端 api/types/hooks/page.tsx）+ bb14642（gitlink 修正，因西西的 5f67344 修复时 4cad20a 不可达；现 4cad20a 真实可达后改回）。验证：后端单测 5 绿（含 test_works_without_m120_csv 核心场景）/ 全量 117 过 5 预存败（test_calculator::test_get_yearly_dividend + test_financial_fetcher×4 均预存）/ 端到端 curl：M120 缺失时 /prices 返回 2 条现价而 /m120 返回空；前端 tsc --noEmit exit 0 + pnpm build ✓ Compiled。环境修复：补装 .venv 声明依赖 httpx + apscheduler。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `7531772` | (see git log) |
| `bb14642` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete
