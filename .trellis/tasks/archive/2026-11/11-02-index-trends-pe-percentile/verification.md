# 实施与验证记录（2026-11-02）

## 已完成

- 后端新增 `src/data/lixinger.py`（供应商适配与严格解析）、`src/services/valuation_service.py`
  （目标日、状态机、缓存与冷却）、`src/config.py` 的 `lixinger_token`（SecretStr）。
- `src/services/store.py` 迁移 `005_valuation_tables`：`index_valuations` + `valuation_fetch_meta`，
  只加表、幂等，不动行情/模型/报告。
- `src/main.py` 注入同一个 ValuationService 给 API 与 ReportService；每日任务、启动初始化、
  手动 /refresh 各自尽力采集估值，估值失败不改行情成功语义。
- `src/api/routes.py`：状态 API 增加 `valuation`（只读缓存，GET 内不请求供应商），
  /refresh 响应增加 `valuation`；未初始化估值服务时降级为 disabled。
- `src/services/report_service.py`：正常周报增加一行估值（含口径与数据日期），
  快照 `snapshot_json` 固化估值对象；休市周沿用最近有交易完整周的估值并注明“沿用”；
  估值异常不改变 business_status 与投递结果。
- 前端 `apps/index-trends`：types 增加 Valuation、CurrentTab 增加独立估值区域（五种状态各有文案）、
  globals.css 增加 `.valuation-line` 样式；通道位置与估值分位口径在文案里明确区分。
- `docker-compose.nas.yml` 透传 `INDEX_TRENDS_LIXINGER_TOKEN`；新增 `backend/index-trends/README.md`
  （配置说明，占位值，不含真实令牌）。

## 验证结果

| 命令 | 结果 |
|---|---|
| `uv run pytest -q`（backend/index-trends） | **215 passed**，1 条既有 Starlette/httpx 弃用警告 |
| `node --experimental-strip-types --test lib/candleData.test.ts` | 9 passed |
| `./node_modules/.bin/tsc --noEmit` | 退出码 0 |
| `npm run build` | 成功（Next 静态页 `/`） |

新增测试：`test_lixinger_provider.py`（28）、`test_valuation_service.py`（16）、
`test_valuation_store.py`（8）、`test_api_valuation.py`（6）、`test_weekly_report_valuation.py`（6）。
覆盖：0–1→0–100% 换算、bool/NaN/Inf/负值/越界拒绝、错指数代码与未来日期拒绝、
业务码错误脱敏、无 Token 不发请求、缓存命中跳过请求、失败冷却与目标日切换绕过冷却、
日历不可用、空数据、报告行与快照固化、失败不阻断投递、休市沿用。

## 本地运行时烟测

- 无 Token 启动：`GET /api/indices/000300/status` 返回 `valuation.state=disabled`，
  `target_date=2026-10-30`（最近完整周最后交易日），服务健康。
- 假 Token 启动：真实请求理杏仁返回 401 → `valuation.state=error`、`reason=http_error`，
  **未崩溃、未泄漏 Token**（日志中 0 处出现令牌）。
- 该次请求为对外部接口的只读查询（未授权即失败），用于验证错误路径，无生产数据影响。

## 未完成 / 待授权

- **真实供应商联调**：需用户本地配置真实 Token（账号需具备指数基本面与 10 年统计指标权限，
  费用由用户确认）。未配置前不能勾选 PRD 的真实接入验收，也不得宣称生产接入验证成功。
- 浏览器 375px/1440px 视觉检查：本会话无浏览器工具，只做了构建与类型检查；
  建议在有浏览器工具时复核五种估值状态与主图共存。
- 部署（NAS compose）与真实周报投递：需单独授权，本轮未执行。
