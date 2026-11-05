# 验收记录（11-04-index-trends-daily-valuation）

> 记录实际执行的验证命令与结果。真实环境证据缺失的验收项明确标未验证。

## 命令与结果

| 命令 | 结果 |
|---|---|
| `cd backend/index-trends && uv run pytest -q` | **237 passed**（脱网，约 5 分钟） |
| `cd apps/index-trends && ./node_modules/.bin/tsc --noEmit` | 通过 |
| `cd apps/index-trends && npm run build` | 通过（Next 静态构建成功） |
| `cd apps/index-trends && node --experimental-strip-types --test lib/candleData.test.ts` | 9 passed |
| compose 结构检查（只输出 env key 列表） | `INDEX_TRENDS_VALUATION_REFRESH_CRON` 与 `INDEX_TRENDS_LIXINGER_TOKEN` 均已透传 |

## 验收项

- [x] **AC1**：独立 `valuation_refresh` job，默认 `30 18 * * mon-fri`（`INDEX_TRENDS_VALUATION_REFRESH_CRON` 可覆盖）；
  16:30 `daily_refresh` 不再调用估值（`test_daily_refresh_does_not_trigger_valuation`）；
  休市日定时采集跳过且不发请求（`test_scheduled_skips_on_holiday_without_request` / `..._on_weekend_...`）。
- [x] **AC2**：目标日可验证——周三收盘后取当日、收盘前取上一交易日、周末取上周五、长假取假期前最后交易日、
  跨年取上一年最后交易日（`test_daily_target_*`）；日历覆盖不足返回 `calendar_unavailable`；
  页面目标日不再受完整周限制。
- [x] **AC3**：18:30 采集成功 → 19:00 周报复用缓存（不再请求供应商）；
  18:30 失败 → 19:00 按冷却规则重试；滞后（供应商只给更早日期）→ 19:00 仍可重试，不算缓存命中；
  失败时用不晚于报告收盘日的缓存并写明实际日期与异常；历史报告不采用收盘日之后的数据。
- [x] **AC4**：启动初始化、手动刷新、无 Token 不发请求、状态 GET 只读、15 分钟冷却、
  并发采集只发一次请求（`test_overlapping_refresh_only_requests_once`）、调度器关闭幂等与任务清理均有脱网测试；
  行情失败与周报失败互相隔离。
- [x] **AC5**：后端全量测试通过；`valuation-contract.md` 与 README 已同步每日口径；
  compose 结构检查通过；前端仅改文案与注释，类型检查与构建通过。
- [ ] **AC6（未验证）**：需要在部署环境核对 18:30 任务实际注册、真实数据日期与周五周报快照。
  本地无真实供应商数据与部署环境证据，**不宣称供应商更新时点已核实**；
  18:30 只是本服务的采集计划时间，供应商是否已更新当日 PE-TTM 需上线后实测。

## 已知限制

- 供应商当日 PE-TTM 的就绪时间未知：18:30 采集若拿不到当日数据，页面与周报会显示
  `stale`（`not_updated_to_target`）并写明实际数据日期，不冒充 `ok`。
- 交易日历覆盖到 2026-12-31；跨年后的目标日解析会返回 `calendar_unavailable`（明确错误，不猜交易日），
  与既有周线管线的覆盖限制一致，需要升级 `pandas_market_calendars` 后重新核验。
