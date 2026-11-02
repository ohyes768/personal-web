# index-trends（宽基趋势观察）

沪深300 线性回归通道 + 每周五 19:00 周报。口径统一为**完整周线**：
周主键是周一（YYYY-MM-DD），行情的 date 是该周实际最后交易日。

- 后端：`backend/index-trends`（FastAPI，端口 8100，API 前缀 `/api`）
- 前端：`apps/index-trends`（Next.js 静态页，basePath `/index-trends`）
- 部署：`docker-compose.nas.yml` 中的 `index-trends-backend` / `index-trends-frontend`

## 环境变量（全部带 `INDEX_TRENDS_` 前缀）

| 变量 | 默认 | 说明 |
|---|---|---|
| `INDEX_TRENDS_DATA_DIR` | `data` | SQLite 目录（`index-trends.db`） |
| `INDEX_TRENDS_SERVICE_HOST` / `_SERVICE_PORT` | `0.0.0.0` / `8100` | 监听地址 |
| `INDEX_TRENDS_PUBLIC_SITE_URL` | 空 | 周报消息里的页面链接前缀，空则不带链接 |
| `INDEX_TRENDS_REPORT_CRON` | `0 19 * * fri` | 周报时间（Asia/Shanghai） |
| `INDEX_TRENDS_DAILY_REFRESH_CRON` | `30 16 * * mon-fri` | 每日行情刷新 |
| `INDEX_TRENDS_LIXINGER_TOKEN` | 空 | 理杏仁访问令牌（沪深300 PE-TTM 近10年分位） |

### 理杏仁估值（可选）

不配置 `INDEX_TRENDS_LIXINGER_TOKEN` 时服务正常启动：页面与周报显示「估值未启用」，
且**不会发起任何理杏仁请求**。配置后：

- 令牌只由后端读取（`SecretStr`），不进入前端响应、日志、数据库与版本库；
- 供应商返回的 PE-TTM（`pe_ttm.mcw`，总市值加权）与近 10 年分位
  （`pe_ttm.y10.mcw.cvpos`，0–1 比例）直接采用，**不在本地重算分位**；
- 数据日期取**最近一个应当完成的自然周的最后交易日**（周五 15:05 收盘后才切到本周）；
- 估值异常（无权限、网络失败、格式异常、日期滞后）不阻断行情、图表与原周报。

本地 `.env` 示例（占位值，不要提交真实令牌）：

```bash
INDEX_TRENDS_LIXINGER_TOKEN=<your-lixinger-token>
```

NAS 部署：在 `.env` 里加 `INDEX_TRENDS_LIXINGER_TOKEN=...`，compose 会透传给
`index-trends-backend`。令牌需具备指数基本面与 10 年统计指标权限，费用与开通由使用者自行确认。

## 验证命令

```bash
cd backend/index-trends
uv run pytest -q                    # 后端全量回归（脱网）
cd ../../apps/index-trends
node --experimental-strip-types --test lib/candleData.test.ts
./node_modules/.bin/tsc --noEmit
npm run build
```

该包没有独立 lint 脚本，不要写“lint 通过”；`npm run build` 日志里的
“Linting and checking validity of types” 是 Next 构建步骤。
