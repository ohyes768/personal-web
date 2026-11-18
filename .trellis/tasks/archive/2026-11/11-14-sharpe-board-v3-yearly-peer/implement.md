# 执行计划：夏普榜单 v3 年度同类排名 + 历史回溯

## 前置阅读

- `.trellis/spec/backend/fund-select/backend/contracts.md` §13（周榜）、§18（v2）
- 本任务 `prd.md` / `design.md`
- 参考实现：`scripts/backfill_sharpe_board_ext.py`（回溯骨架，已具备按周算夏普 + TRI 合成 + 缓存）

## 测试环境

```bash
cd backend/fund-select
/tmp/fsvenv/bin/python -m pytest tests/ -q        # 668 passed 为基线
cd apps/fund-select
node --experimental-strip-types --test src/lib/*.test.ts   # 37 passed 基线
npx tsc --noEmit
```

---

## 阶段 0：基线

- [ ] 0.1 后端全量测试，确认 668 passed
- [ ] 0.2 前端 node --test + tsc，确认 37 passed
- [ ] 0.3 记录生产库现状：v2 weeks=2 / observations=36，v1=0（作为「不受影响」的对照）

**回滚**：无改动。

---

## 阶段 1：年度窗口与冻结（纯逻辑，先写测试）

### 1.1 `yearly_window(ref_year)`

- [ ] `sharpe_capture.py` 新增常量 `YEARLY_WINDOW=3`、`MIN_YEARLY_TOP_PCT=25.0`、`MIN_YEARLY_YEARS=2`
- [ ] `yearly_window(ref_year: int) -> list[str]` 返回最近 3 个已完成年度
- [ ] 默认 `ref_year=date.today().year`

**测试**：
- [ ] 2026 → `["2023","2024","2025"]`
- [ ] 2027 → `["2024","2025","2026"]`
- [ ] 边界：2024 → `["2021","2022","2023"]`

### 1.2 `freeze_yearly_peer_rows`

- [ ] 批量 `in_` 查询 `(code, period in window, period_kind='年度业绩')`
- [ ] 解析分位（复用 `_parse_peer_percentile`）
- [ ] 返回 `{code: {years, qualified_years, yearly_top_pct, qualified, window}}`
- [ ] **不做 as_of 陈旧判断**
- [ ] 缺失年份记 `None`，不计入达标年数

**测试**：
- [ ] 三年均前 25% → `qualified_years=3, qualified=True`
- [ ] 2 年前 25%、1 年后 50% → `qualified=True`
- [ ] 1 年前 25% → `qualified=False`
- [ ] 某年无数据 → 计入 `None`，达标年数不含该年
- [ ] 分位恰好 25.0 → 算达标（含等号）
- [ ] 格式异常 `''`/`'abc'`/`'0/100'` → 该年 `None`
- [ ] ref_year 注入：2027 年窗口正确切换
- [ ] 500+ codes 分块不报错

---

## 阶段 2：谓词与 profile

### 2.1 `entry_predicate` 扩展

- [ ] 加 `min_yearly_top_pct=None` / `min_yearly_years=None`
- [ ] 判定 `qualified_years >= min_yearly_years`（含等号）
- [ ] None → 不命中
- [ ] 两参数默认 None 时 v1/v2 行为逐字节不变

**测试**：
- [ ] 默认 None → 与改动前一致（回归锁）
- [ ] `qualified_years=2, min_yearly_years=2` → 通过
- [ ] `qualified_years=1` → 不通过
- [ ] `qualified_years=None` → 不通过

### 2.2 v3 profile

- [ ] `ALGORITHM_VERSION_V3 = "risk-3y-v3"`
- [ ] 新增 `(stock, v3)` / `(discovery-stock, v3)`，filters = v1 五条件 + 两个年度参数
- [ ] v1/v2 一字不改

**测试**：
- [ ] v3 filters 含 `min_yearly_top_pct=25.0`、`min_yearly_years=2`
- [ ] v1/v2 filters 未变（硬编码断言）
- [ ] v3 algorithm_version 与 v1/v2 都不同

---

## 阶段 3：接线与发布

- [ ] `tasks.py`（stock）：`capture.peer_rows = freeze_yearly_peer_rows(db, codes)`
- [ ] `market_full_pipeline.py`：L5 之后同样调用
- [ ] `publish_week_board`：谓词输入合并 `qualified_years`
- [ ] `gate_missing` 诊断按年度口径记录
- [ ] `evidence_json` 存 `years` / `qualified_years` / `yearly_top_pct` / `window`

**测试**：
- [ ] 年度达标的数据能入选，不达标被挡
- [ ] 缺年数据进入 gate_missing 诊断
- [ ] v2 profile 仍忽略新参数（兼容）

---

## 阶段 4：展示与默认切换

- [ ] `aggregate_board` 从 evidence 读年度数据
- [ ] DTO 加 `peer_years` / `peer_qualified_years` / `peer_window`，保留 `peer_pct`
- [ ] `item_keys` 同步加字段
- [ ] 默认版本切 v3（周任务 / API / 聚合）

**测试**：
- [ ] API 返回新字段
- [ ] 无年度数据 → 全部 null 而非 0

---

## 阶段 5：前端

- [ ] 「同类分位」列改渲染 `2/3 年`，hover 显示各年分位
- [ ] 规则文案：「近3个完整年度中至少2年前25%」
- [ ] 默认版本 v3

**测试**：
- [ ] `describeEntryFilters` 渲染年度口径
- [ ] 默认 v3
- [ ] `tsc --noEmit` + `pnpm build`

---

## 阶段 6：回溯脚本

### 6.1 `scripts/backfill_v3_yearly_peer.py`

基于 `backfill_sharpe_board_ext.py`，差异：

- [ ] `PROFILE_VERSION = "v3"`
- [ ] 谓词参数用 v3 filters
- [ ] 年度排名一次冻结、全周共享（不随周变化）
- [ ] 周范围默认 `2025-01-06` ~ 最新完整周
- [ ] 幂等：已存在 complete 周跳过
- [ ] `--publish` 才写库，默认 dry-run
- [ ] 净值/基准 pickle 缓存复用

**测试**（`tests/test_backfill_v3.py`，mock 网络）：
- [ ] 幂等：重复跑不重复写
- [ ] 周键全部落在周一
- [ ] dry-run 不写库
- [ ] **v2 数据不受影响**（跑前后 v2 行数一致）

### 6.2 实际执行（人工确认）

- [ ] 生产库备份
- [ ] dry-run 看覆盖周数与预计入选数
- [ ] `--publish` 执行
- [ ] 验证：v3 weeks ≈ 45+，v2 weeks 仍为 2

---

## 阶段 7：收尾

- [ ] 后端全量测试
- [ ] 前端测试 + tsc + build
- [ ] 部署验证（API 默认 v3、weeks 长度、series 非 null 点数）
- [ ] 浏览器验证两列渲染
- [ ] 契约 §19 + 前端契约 §8
- [ ] journal + 归档

---

## 回滚点

| 阶段 | 回滚 |
|---|---|
| 1-5 | `git revert`；v1/v2 数据未动 |
| 6 回溯 | `DELETE FROM sharpe_board_* WHERE profile_version='v3'` 重跑或放弃 |
| 默认版本 | 改 `BOARD_PROFILE_VERSION="v2"` 一行 |

---

## 验收命令

```bash
cd backend/fund-select
/tmp/fsvenv/bin/python -m pytest tests/ -q
cd apps/fund-select
node --experimental-strip-types --test src/lib/*.test.ts
npx tsc --noEmit && pnpm build

# 回溯（容器内）
python scripts/backfill_v3_yearly_peer.py --nav-cache /tmp/nav.pkl --bench-cache /tmp/bench.pkl
python scripts/backfill_v3_yearly_peer.py --publish --nav-cache /tmp/nav.pkl --bench-cache /tmp/bench.pkl
```
