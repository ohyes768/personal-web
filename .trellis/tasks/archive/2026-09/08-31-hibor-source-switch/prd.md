# HIBOR 数据源从 HKMA 切换到 akshare 并接入日频区块

## Goal

HKMA 公开 API 当前 504 不可用，HIBOR 数据停更约 5 个月（hibor.csv 最新 2026-04-08）。切换数据源为 akshare.rate_interbank（东方财富源，Hibor港币 隔夜），保持 hibor.csv 列名 / 数据契约不变；接入到日频快照 exchange_rate 维度；前端 DAILY_GROUPS / INDICATOR_LABELS / INDICATOR_LINK_MAP 同步新增。

## 背景

- 当前实现：`backend/macro/src/services/hibor_service.py` 直连 HKMA `daily-figures-interbank-liquidity`，单字段 `hibor_overnight`。
- 已实测验证：HKMA 域名 (`api.hkma.gov.hk`) 现在 GET 504（ALB 网关超时，约 70s）。
- akshare demo 实测：`rate_interbank(market='香港银行同业拆借市场', symbol='Hibor港币', indicator='隔夜')` 正常返回，今日数据 4.099%，覆盖 5000+ 行。
- 已有 HTTP 端点 `/fetch/hibor/history`、`/update/hibor`、`/health` 等均沿用。
- 已有 CSV 列名 `HIBOR_Overnight`，与 `EconomicData.hibor` 前端字段对齐（前端类型 economic.ts:91 注释「单位：%」）。

## Requirements

### 后端

1. **`hibor_service.py`**：改造 `fetch_series` 改用 akshare 拉取（market/symbol/indicator 固定为 `香港银行同业拆借市场/Hibor港币/隔夜`），输出 Series 保持 `name="hibor_overnight"`，签名不变。
2. **CSV 列保持 `HIBOR_Overnight`**：`save_fred_data(..., key="hibor")` 现成行为不动（column 名取自 Series.name 即可，确保输出列名 = `hibor_overnight` → 现有 CSV 约定是 `HIBOR_Overnight`，需要验证或调整）。
3. **失败处理**：保留 `fetch_series` 现有 `@async_retry(max_retries=3, delay=1.0)` 重试；空数据走现有「底库过期判别」helper（routes.py 1491-1626 既有逻辑）。
4. **scheduler / 路由 / 模型**：零改动（HIBORData / HIBORUpdateData 沿用；scheduler.json 中 `initLiquidityHistory/updateLiquidity` 沿用）。

### 前端

5. **日频快照**：`_DAILY_INDICATORS.exchange_rate` 加入 `("hibor_overnight", "load_data:hibor", "HIBOR_Overnight")`，与后端 hibor.csv 列名对齐。
6. **前端常量同步**：
   - `constants.ts DAILY_GROUPS.exchange_rate.indicators` 加 `hibor_overnight`
   - `constants.ts INDICATOR_LABELS['hibor_overnight']` 加 `{ label: 'HIBOR 隔夜', unit: '%', digits: 3 }`
   - `constants.ts INDICATOR_LINK_MAP['hibor_overnight'] = 'liquidity-risk'`（**已确认**：日频卡显示 📈 跳到已画 HIBOR 的 Tab）
7. **历史数据回填**：执行时跑一次 `/fetch/hibor/history` 全量回补（**已确认**：akshare 5000+ 行覆盖到 1990s，一次干完）。原有 HKMA 数据（截止 2026-04-08）会被覆盖。新数据源列名仍是 `HIBOR_Overnight`，前端 `EconomicData.hibor` 读取路径不变。

### 不在范围

- 不改其他数据源（TGA/VIX/TED/汇率等）
- 不动 LiquidityTab / MacroSignalTab 等前端 UI
- 不扩 HIBOR 多期限（只 隔夜 一档，akshare 同时支持 1W/1M/3M 等，但本次不开）
- 不切回 HKMA（即使 HKMA 恢复）

## Acceptance Criteria

- [ ] `backend/macro/.venv/bin/python -c "import akshare as ak; print(ak.__version__)"` ≥ 1.18（已有）
- [ ] `hibor_service.py` 使用 akshare 实测可在 60s 内返回 ≥ 100 行
- [ ] `/fetch/hibor/history` 跑通，hibor.csv 末尾追加 ≥ 1 行新日期，列名为 `HIBOR_Overnight`
- [ ] `/update/hibor` 跑通返回 success
- [ ] `daily_snapshot_service.py` 的 `get_daily_snapshot()` 返回值中 `groups.exchange_rate.indicators` 含 `key='hibor_overnight'` 的项，`value` 与 `data_date` 非 null（基础 CSV 充足时）
- [ ] 前端常量 `DAILY_GROUPS` / `INDICATOR_LABELS` / `INDICATOR_LINK_MAP` 同步完成；类型 `MacroSignalTab` 编译通过
- [ ] 后端 pytest（`tests/test_incremental_empty.py` 已有 hibor 路径 mock）不破坏
- [ ] `apps/macro pnpm build` 通过；无 console.log

## Notes

- 双源风险：HKMA 恢复后若想回落，可在 hibor_service 里加 source 切换开关（本次不做，避免越界）。
- akshare 在 akshare 1.18.94 中函数符号是 `Hibor港币`（港币非港元），已实测。
- 中文列名是 akshare 返回的 `报告日/利率/涨跌`，落 CSV 时保留 `HIBOR_Overnight` 单列（沿用原约定）。
- 轻量任务（设计要点内聚于 PRD），PRD-only。
