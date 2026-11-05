# index-trends（宽基趋势观察）

沪深300 线性回归通道与估值数据服务。模型拟合使用**完整周线**：
周主键是周一（YYYY-MM-DD），行情的 date 是该周实际最后交易日。

- 后端：`backend/index-trends`（FastAPI，端口 8100，API 前缀 `/api`）
- 前端：`apps/index-trends`（Next.js 静态页，basePath `/index-trends`）
- 部署：`docker-compose.nas.yml` 中的 `index-trends-backend` / `index-trends-frontend`

每日行情与估值刷新继续由 Web 后端负责，默认工作日16:30（Asia/Shanghai），启动时仍初始化估值。
Hermes 通过查询 API 获取缓存，负责简报生成、定时与钉钉/RSS投递；本服务不再生成或发送周报，也不在启动时补发。
页面手动刷新 `POST /api/refresh` 保留；GET 查询不会触发刷新。

旧 `GET/PATCH /api/report-settings` 和 `POST /api/report-jobs/{job_id}/run` 已移除（404）。
`GET /api/reports` 仅用于读取历史周报；已有 SQLite 周报、配置与尝试记录保留，不删表、不清历史数据。
旧 `INDEX_TRENDS_DINGTALK_WEBHOOK_URL`、`INDEX_TRENDS_PUBLIC_SITE_URL`、`INDEX_TRENDS_REPORT_CRON` 已不再使用，可从部署环境中移除。
代码变更需重建并部署后端后才在服务器生效。

## 环境变量（全部带 `INDEX_TRENDS_` 前缀）

| 变量 | 默认 | 说明 |
|---|---|---|
| `INDEX_TRENDS_DATA_DIR` | `data` | SQLite 目录（`index-trends.db`） |
| `INDEX_TRENDS_SERVICE_HOST` / `_SERVICE_PORT` | `0.0.0.0` / `8100` | 监听地址 |
| `INDEX_TRENDS_DAILY_REFRESH_CRON` | `30 16 * * mon-fri` | Web 后端每日行情与估值刷新 |
| `INDEX_TRENDS_LIXINGER_TOKEN` | 空 | 理杏仁访问令牌（沪深300 PE-TTM 近10年分位） |

### 理杏仁估值（可选）

不配置 `INDEX_TRENDS_LIXINGER_TOKEN` 时服务正常启动：估值状态为 `disabled`，
且**不会发起任何理杏仁请求**。配置后：

- 令牌只由后端读取（`SecretStr`），不进入前端响应、日志、数据库与版本库；
- 供应商返回的 PE-TTM（`pe_ttm.mcw`，总市值加权）与近 10 年分位
  （`pe_ttm.y10.mcw.cvpos`，0–1 比例）直接采用，**不在本地重算分位**；
- 数据日期取**最近一个应当完成的自然周的最后交易日**（周五 15:05 收盘后才切到本周）；
- 估值异常（无权限、网络失败、格式异常、日期滞后）不阻断行情、图表与查询服务。

本地 `.env` 示例（占位值，不要提交真实令牌）：

```bash
INDEX_TRENDS_LIXINGER_TOKEN=<your-lixinger-token>
```

NAS 部署：在 `.env` 里加 `INDEX_TRENDS_LIXINGER_TOKEN=...`，compose 会透传给
`index-trends-backend`。令牌需具备指数基本面与 10 年统计指标权限，费用与开通由使用者自行确认。

## 对外查询 API（Hermes / 脚本）

一次 GET 即可获取沪深300 当前周线通道位置和 PE-TTM 近10年分位，复用网页的状态接口。
GET 只读本地缓存，不触发供应商采集、模型重算或消息发送。

```bash
curl --fail-with-body 'https://web.duomi77.cn:9443/api/index-trends/indices/000300/status?model=trailing_10y_weekly'
```

本地后端使用 `http://localhost:8100/api/indices/000300/status?model=trailing_10y_weekly`。
`model` 必填：`trailing_10y_weekly` 为近10年周线模型，
`since_inception_weekly` 为上市以来周线模型。两个模型共享同一份估值。
指数代码为字符串，当前仅支持 `000300`。

| 响应字段 | 含义 |
|---|---|
| `available` / `reason` | 通道是否可用及不可用原因；不可用时不保证存在价格、轨道和位置字段 |
| `model_kind` / `model` | 选用的周线模型及其拟合信息 |
| `price_as_of` / `close` | 最近已收盘交易日及收盘价，不是盘中价格 |
| `projection_week` | 价格所在自然周的周一；进行中的周也可投影到已有周线通道 |
| `lower` / `mid` / `upper` | 该周的下轨、中轨、上轨 |
| `position_pct` | `(close-lower)/(upper-lower)*100`；下轨为0、上轨为100，突破时可小于0或大于100 |
| `region` | `below_channel` / `lower` / `middle` / `upper` / `above_channel`，依次表示通道下方、低位、中部、高位、通道上方 |
| `data_status` / `snapshot_id` | 行情新鲜度、异常原因与快照标识；`available=true` 不代表数据一定新鲜 |
| `valuation.state` / `valuation.reason` | 估值状态：`ok` / `stale` / `empty` / `error` / `disabled` 及原因 |
| `valuation.pe_ttm` | 总市值加权 PE-TTM，缺失为 `null` |
| `valuation.percentile_pct` | 理杏仁近10年 PE-TTM 分位，0—100（不是0—1比例），缺失为 `null` |
| `valuation.target_date` / `valuation.as_of` | 估值期望日期与实际数据日期 |
| `valuation.source` / `valuation.metric` / `valuation.window` | 供应商与统计口径 |

通道位置使用最近已收盘交易日的价格，估值目标日为最近应当完成的自然周的最后交易日，
两者日期可能不同。调用方应分别标注 `price_as_of` 与 `valuation.as_of`，
并检查 `data_status` 和 `valuation.state`；估值异常不表示通道也不可用。
`error` 状态可以携带缓存估值，必须标注更新失败；`disabled` 表示未配置估值服务，不能当成零分位。

接口沿用现有公开只读访问方式，不需要把理杏仁令牌传给调用端。
不支持的指数返回404，非法模型返回400，缺少必填参数返回422，趋势服务未初始化返回503。
HTTP 200仍需检查上述业务状态；这里的访问约定仅针对本查询接口。

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
