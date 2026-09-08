# 修复 ranking ETL 白名单遗漏混合型

## Goal

修复 stock ranking ETL bug：funds_stock.yaml 里的 42 只混合型基金（混合型-灵活配置 22 + 混合型-偏股 20）从未被雪球抓 ranking。改为 `fetch_ranking` 参数（沿用 fetch_holdings 模式），由调用方控制：refresh_stock_funds_sync 传 True（对 funds_stock.yaml 142 只全抓），refresh_configured_funds_sync 不传（默认 False，债基永不抓）。重抓数据 + 测试覆盖 + 验证覆盖率 100%。

## Background（已确认事实）

- **Bug 位置**：`backend/fund-select/src/services/refresh_service.py:97-106`：
  ```python
  # 5. 业绩排名（仅股票型 + QDII，避免对债基空跑）
  fund_type = out["fund_type"]
  if fund_type.startswith("股票型") or fund_type.startswith("QDII") or fund_type == "QDII":
      try:
          ach_df = fetch_achievement(code)
          ...
  ```
- **覆盖现状（实测 2026-09-08）**：
  - funds_stock.yaml 142 只活跃基金
  - **42 只混合型**（30%）ranking 表 0 行
    - 混合型-灵活配置 22 只（如 000480 / 001856 / 003598 / 519195 等）
    - 混合型-偏股 20 只（如 008318 / 010350 / 090013 等）
  - 100 只（股票型 + QDII）ranking 正常覆盖
- **真实案例**：003598 华商润丰灵活A（混合型-灵活配置）`/api/funds/stock/003598` 返回 `achievement_ranks: 0 行`
- **修复策略：fetch_ranking 参数**（与 fetch_holdings 同模式）：
  - snapshot_fund 加 `fetch_ranking: bool = False` 参数
  - refresh_stock_funds_sync 调用时传 True（funds_stock.yaml 全名单）
  - refresh_configured_funds_sync 不传（默认 False，funds.yaml 债基永不抓）
- **scheduler**：`tasks.py:94-158 refresh_stock_funds_sync` 已经遍历 funds_stock.yaml 全名单（不去重），传 fetch_ranking=True 后无需修改调度逻辑
- **测试现状**：`tests/test_refresh_service.py:74-77 test_default_ignores_fund_type` 验证"债基路径不抓 holdings"（默认 fetch_holdings=False）；ranking 行为无单测覆盖，需补

## User Value

- 股票 tab 列表 42 只混合型基金**显示真正的同类排名**，与已有 100 只股票型/QDII 一致
- "大热必死"分析对混合型也生效（混合型常因股票仓位高而进 top 名单）
- 消除"看起来是 bug"的不一致（同一 tab 里部分基金有排名、部分没有）
- 数据架构清晰：ranking 抓取 = 调用方决策，不再嵌入 fund_type 隐式判断

## Requirements

### REQ-1 修复 refresh_service.py 引入 fetch_ranking 参数

- `snapshot_fund` 签名加 `fetch_ranking: bool = False` 参数（沿用 `fetch_holdings` 命名风格）
- 改写 refresh_service.py:97-106：
  ```python
  # 改前
  fund_type = out["fund_type"]
  if fund_type.startswith("股票型") or fund_type.startswith("QDII") or fund_type == "QDII":
      try:
          ach_df = fetch_achievement(code)
          if not ach_df.empty:
              out["achievement"] = ach_df
              out["achievement_as_of_date"] = ref.date()
      except Exception as e:
          logger.warning("achievement_xq 失败 %s: %s", code, str(e)[:150])

  # 改后
  if fetch_ranking:
      try:
          ach_df = fetch_achievement(code)
          if not ach_df.empty:
              out["achievement"] = ach_df
              out["achievement_as_of_date"] = ref.date()
      except Exception as e:
          logger.warning("achievement_xq 失败 %s: %s", code, str(e)[:150])
  ```
- 注释更新：原注释"仅股票型 + QDII，避免对债基空跑"删除，改为"由调用方控制（stock 路径开启，债基路径关闭）"
- **债基路径天然隔离**：`refresh_configured_funds_sync`（funds.yaml 债基）不传 fetch_ranking，ranking 块永不执行

### REQ-2 调用方更新

- `scheduler/tasks.py:94-158 refresh_stock_funds_sync`：
  - 调用 `snapshot_fund(..., fetch_ranking=True)`
  - 函数 docstring 注释"（仅股票型 + QDII）"删除/改为"（funds_stock.yaml 全名单，含混合型）"
- `refresh_configured_funds_sync`（债基）：调用 `snapshot_fund` 不传新参数（默认 False），**无需改动**

### REQ-3 测试覆盖

- `tests/test_refresh_service.py` 现有 `_run_snapshot` 辅助函数扩展：增加 `fetch_ranking` 参数
- 新增 5 个测试用例：
  - `test_stock_path_fetches_ranking_for_mixed_flexible`：fund_type="混合型-灵活配置" + fetch_ranking=True → 调用 fetch_achievement
  - `test_stock_path_fetches_ranking_for_mixed_partial_equity`：fund_type="混合型-偏股" + fetch_ranking=True → 调用 fetch_achievement
  - `test_stock_path_fetches_ranking_for_stock_type`：fund_type="股票型-标准指数" + fetch_ranking=True → 调用 fetch_achievement（回归）
  - `test_stock_path_fetches_ranking_for_qdii`：fund_type="QDII" + fetch_ranking=True → 调用 fetch_achievement（回归）
  - `test_bond_path_skips_ranking_even_for_stock_typed_funds`：fund_type="股票型-标准指数" + fetch_ranking=False → 不调用 fetch_achievement（债基路径误调用的回归保护）
- 现有 `test_default_ignores_fund_type` 不动（验证的是 holdings 行为，不在本 bug 范围）

### REQ-4 重抓数据

- **触发**：修复后手动调 `POST /api/funds/stock/refresh`（不带 limit），让 142 只基金走完整 ETL 路径
- **监控**：`GET /api/funds/stock/refresh/status?task_id=xxx` 跟踪进度
- **耗时预期**：funds_stock.yaml 142 只 × ~3-5 秒/只（含 fetch_achievement 雪球调用 + commit），总耗时 7-12 分钟
- **断点续传**：现有 `refresh_stock_funds_sync` 单只立即 commit（tasks.py:144），中断后可重跑
- **进度面板**：前端 refresh status popover 已支持（不需前端改动）

### REQ-5 覆盖率验证

- 重抓完成后，实测 funds_stock.yaml 142 只活跃基金中 **ranking 0 行的基金数应为 0**（或仅含 fetch_achievement 本身失败的极少数，可手动重跑）
- 抽样验证：003598 / 002943 / 519195 三只修复前 0 行的混合型，重抓后应有完整 achievement_ranks（4 周期 + 历年）
- HTTP 实测：`curl /api/funds/stock/003598` 返回 achievement_ranks ≥ 10 行

## Acceptance Criteria

| ID | 标准 | 映射 REQ |
|---|---|---|
| AC-1 | refresh_service.py snapshot_fund 签名有 `fetch_ranking: bool = False` 参数 | REQ-1 |
| AC-2 | snapshot_fund 内 ranking 抓取逻辑由 `if fetch_ranking:` 控制（不再依赖 fund_type 判断） | REQ-1 |
| AC-3 | scheduler/tasks.py refresh_stock_funds_sync 调用 snapshot_fund 时传 `fetch_ranking=True` | REQ-2 |
| AC-4 | refresh_configured_funds_sync 调用 snapshot_fund 不传新参数（债基路径永远不抓 ranking） | REQ-1, REQ-2 |
| AC-5 | pytest 全量通过（含原有 171 + 新增 5 用例 = 176 passed；容忍 1 个预存在 cbond 失败） | REQ-3 |
| AC-6 | 重抓完成后 funds_stock.yaml 142 只活跃基金中 ranking 0 行数 ≤ 2 只（容忍个别雪球接口失败） | REQ-4, REQ-5 |
| AC-7 | 抽样 003598 stock detail 接口 achievement_ranks ≥ 10 行（4 周期 + 若干年度） | REQ-5 |
| AC-8 | 抽样 002943 / 519195 同 AC-7 | REQ-5 |
| AC-9 | ruff / mypy 等无新增警告 | REQ-1, REQ-2 |

## Non-Goals

- ❌ 不改 funds_stock.yaml / funds.yaml 名单（保持现状）。
- ❌ 不在 ranking 抓取逻辑里加 fund_type 判断（彻底走调用方参数化路径）。
- ❌ 不做自然月 / 自定义区间排名（之前任务 deferred）。
- ❌ 不动前端（DTO 已支持，前端零改动）。
- ❌ 不实现"白名单"配置化（用户决策去掉白名单，不留口子）。

## Technical Notes

- **fetch_ranking 与 fetch_holdings 对称**：
  - `fetch_holdings=True` 由 refresh_configured_funds_sync（债基）传；stock 路径传 False
  - `fetch_ranking=True` 由 refresh_stock_funds_sync（stock）传；债基路径不传（默认 False）
  - 两个参数互不相关，按调用方需求独立
- **调用入口天然隔离**：
  - `refresh_configured_funds_sync`（funds.yaml 债基）→ `snapshot_fund(..., fetch_holdings=True)` 不传 fetch_ranking → 债基不抓 ranking
  - `refresh_stock_funds_sync`（funds_stock.yaml）→ `snapshot_fund(..., fetch_holdings=False, fetch_ranking=True)` → 142 只全抓 ranking
- **fetch_achievement 雪球接口**：对混合型也返回同类排名（实测 `ak.fund_individual_achievement_xq("003598")` 返回 32 行），无副作用
- **更新注释**：refresh_service.py docstring 也提到"基金业绩排名仅在 stock 路径抓取"

## Risks / Rollback

- **风险 1**：snapshot_fund 漏改某个调用方 → 已 grep 确认仅 2 处调用（tasks.py:63 refresh_configured / tasks.py:132 refresh_stock）；均同步更新。
- **风险 2**：重抓期间触发雪球频率限制 → 重抓 142 只 × ~3 秒 ≈ 7-12 分钟，按经验 1 QPS 即可安全；如报错则自动重试 3 次（MAX_RETRY_PER_FUND）。
- **风险 3**：刷库过程中前端调用接口返回部分缺失 → 重抓是 BackgroundTasks，前端用户感知不强；列表缓存仅 total 字段反映进度。
- **风险 4**：某些混合型雪球仍返回空（极个别新发基金）→ 容忍 ≤ 2 只 0 行；个别情况可通过再次 refresh 补齐。
- **回滚**：
  - 代码回滚：snapshot_fund 加回 `fund_type.startswith("股票型")` 判断；refresh_stock_funds_sync 不传 fetch_ranking。
  - 数据回滚：funds_stock.yaml 名单不变；ranking 表只多不删（最差情况是 ranking 行为和现在一样）。

## Open Questions（已解决）

- ✅ **修复方案**：去掉白名单 → 改为 `fetch_ranking` 参数
- ✅ **任务流程**：创建 Trellis 任务并修复
