# phase2-B 实施清单

## 前置确认

- [x] phase2-A 已 archive（fund_benchmark 109,602 行 / risk_free_rate 6,162 行已落库）
- [ ] design.md 已 review（nav 口径=累计净值 / T-M numpy 实现 / 容错判据）

## 实施步骤

### Step 1: fetch_nav_accumulated + 单测
- [ ] `src/data/nav_fetcher.py` 追加 `fetch_nav_accumulated(code)`（indicator="累计净值走势"，升序）
- [ ] `tests/test_data_fetchers.py` 或新文件补契约测试（mock akshare）
- [ ] 验证：`pytest tests/ -q` 全过

### Step 2: FundRiskMetrics model
- [ ] `src/db/models.py` 追加（见 design）
- [ ] 验证：init_db 后 `fund_risk_metrics` 表存在

### Step 3: compute_risk_metrics 纯函数 TDD
- [ ] 先写 `tests/test_risk_service.py`：
  - 已知序列精确断言（sharpe/ir/excess）
  - T-M 精确二次恢复（构造 y = 0.001 + 0.8x + 0.5x²）
  - 容错：样本<250 / std=0 / R_b 空 → None
- [ ] 实现 `src/services/risk_service.py: compute_risk_metrics`
- [ ] 验证：RED→GREEN

### Step 4: refresh_fund_risks 编排
- [ ] `risk_service.py` 追加编排（fetch nav + DB 读 bench/rf + compute + upsert）
- [ ] `scheduler/tasks.py`：refresh_stock_funds_sync 末尾（benchmark 步骤后）追加调用
- [ ] 不动 refresh_configured_funds_sync

### Step 5: 全量跑 + DB 验证
- [ ] 143 只全量：142 只 sample_days>0 且指标非 NULL；968157 全 NULL
- [ ] 抽查 3 只（005827 / 161725 / 一只 QDII）指标量级 sanity check

### Step 6: API 字段
- [ ] `src/api/routes.py` stock 响应加 6 字段（sharpe/ir/alpha/gamma/alpha_ir/excess_3y）
- [ ] `tests/test_api.py` 补断言

### Step 7: 前端 6 列
- [x] `/funds/stock` 表格列定义 + 排序 + 空值 "—"（CSV 导出功能已按用户要求整体下线，见 Step 9）
- [x] 验证：`pnpm exec tsc --noEmit` 0 错；build 编译/类型/prerender 6/6 过（standalone symlink EPERM 为 Windows 本机限制，Docker 构建不受影响）

### Step 8: 回归
- [x] `pytest tests/ -q` 109 passed（存量 2 个 fee 失败与本 task 无关）
- [x] 债基页零变化（screen 层宇宙隔离测试全过；仅 FundsHeader 移除 CSV 按钮，属 Step 9）

### Step 9: CSV 导出功能下线（用户 2026-09-03 中途指令）
- [x] 前端：ExportCsvButton.tsx 删除、FundsHeader 两处按钮与 StockExportCsvButton 移除、api.ts 两处 exportCsv 删除
- [x] 后端：/api/funds/export/csv 与 /api/funds/stock/export/csv 路由删除、export_service.py 删除
- [x] 测试：test_api.py TestExportCsv 删除、test_universe_isolation.py CSV 测试改写为 screen 层断言（保留宇宙隔离验证意图）
- [x] 全残留 grep 为空；pytest 109 passed

## Review Gates

| Gate | 时机 | 检查 |
|---|---|---|
| G1 指标正确性 | Step 3 | 纯函数数值断言全过（含 T-M 恢复） |
| G2 全量数据 | Step 5 | 142 非 NULL + 抽查量级合理 |
| G3 前后端 | Step 7 | tsc/build 过 + 页面 6 列可见 |
| G4 回归 | Step 8 | pytest 全过 + 债基零变化 |

## 回滚

`git checkout` 代码 + `DROP TABLE fund_risk_metrics`；不动 A 的表与数据。

## Notes

- 不修第一阶段 ret/dd 的单位净值口径（已知差异，design 有记录，另开 task）
- 不引入 statsmodels / scipy 新依赖（numpy lstsq 够用）
- 债基路径零改动
