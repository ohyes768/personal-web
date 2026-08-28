# 技术设计 — 宏观页面访问性能优化

## 改动边界

| 层 | 文件 | 改动 |
|----|------|------|
| nginx | `nginx/web.conf` | http 块加 gzip 配置 |
| 后端 | `backend/macro/src/main.py` | 加 GZipMiddleware |
| 后端 | `backend/macro/src/api/routes.py` | `get_data` / `health_check` 改线程池执行；`get_data` 加 Cache-Control |
| 前端 | `apps/macro/src/lib/hooks/useFullEconomicData.ts` | 分层加载；移除 localStorage 缓存 |

不改：API 响应结构（`EconomicDataResponse`）、`data_service.py` 的查询/缓存逻辑、CSV 存储与更新流程、各 Tab 组件。

## 1. gzip 压缩（两层都开，互不冲突）

**FastAPI**（`main.py`）：`app.add_middleware(GZipMiddleware, minimum_size=1024)`。
- 覆盖本地 dev（Next rewrites 代理透传 Content-Encoding）和任何直连 8094 的场景。

**nginx**（`web.conf` http 块）：
```nginx
gzip on;
gzip_types application/json text/css application/javascript image/svg+xml;
gzip_min_length 1024;
gzip_comp_level 5;
```
- 不冲突原因：FastAPI 已压缩的响应带 `Content-Encoding: gzip`，nginx 对已有该头的响应不再重复压缩；FastAPI 未压缩的小响应（<1024B）nginx 也不压（min_length）。
- `gzip_types` 默认不含 `application/json`，必须显式加。

## 2. 去阻塞（P0-2）

`routes.py` 两个 handler 从 `async def` 改为 `def`：
- `get_data`（`GET /data`）：FastAPI/Starlette 对同步 handler 自动丢线程池（默认 anyio threadpool），不再阻塞事件循环。`query_data` 内部的 `threading.Lock` 在线程池下语义不变。
- `health_check`（`GET /health`）：循环 11 个 `get_last_date`，每个都 `pd.read_csv` 全量读文件，且是 docker healthcheck 周期调用的端点，同样改 `def`。

不动的：`/signal`、`/months`（只读几个小 JSON 文件，数据量小，不在本任务范围）。

## 3. Cache-Control（P0-3）

`get_data` 响应头加 `Cache-Control: public, max-age=300`（数据日更，5 分钟安全）。
- 实现：handler 签名注入 `response: Response`，`response.headers["Cache-Control"] = "public, max-age=300"`。
- **手动刷新交互**：前端"更新数据"成功后 refreshKey 触发的重新 fetch，URL 与 TTL 内缓存相同会被 disk cache 吞掉。前端 fetch 需带 `{cache: 'reload'}` 强制绕过（仅 refreshKey > 0 时）。
- 不做 ETag：数据日更 + max-age=300 已覆盖热点路径，ETag 需手写 If-None-Match 逻辑，收益边际小，保持简单。

## 4. 前端分层加载（P1）

`useFullEconomicData` 改造（保持对外接口形状，新增 `isFullRange`）：

```
阶段 1（首屏）：getData(<1Y 前>) → setFullData(partial)，isFullRange=false，isLoading=false
阶段 2（后台）：requestIdleCallback（兜底 setTimeout 2s）→ getData('2000-01-01')
             → setFullData(full)，isFullRange=true
手动刷新（refreshKey>0）：直接拉全量（用户明确要新数据），带 {cache:'reload'}
```

- **过滤逻辑零改动**：`useFilteredEconomicData` / `filterDataByTab` 只吃 dates 数组，对短数组天然兼容。
- **ALL 档 loading**：`isFullRange=false` 且当前 timeRange='ALL' 时，Tab 内容区显示"加载全量数据中"占位（page.tsx 传 `isFullRange` 给各 Tab 或在 Tab 内判断——实施时选侵入最小的方式：`useFullEconomicData` 返回 `isFullRange`，由 `useFilteredEconomicData` 消费方在 ALL 时降级显示 loading）。
- **localStorage 移除**：`max-age=300` 的 HTTP disk cache 已覆盖"TTL 内二次访问"热点；localStorage 存全量 JSON 的代价是主线程同步 parse 几 MB + 写入超配额。删除读写逻辑（`FULL_DATA_CACHE_KEY` 相关），`isCached` 返回值保留、恒为 `false`（不动的 UI 引用，实施时 grep 确认 `isCached` 的展示位置）。
- 两次请求总传输 ≈ 全量 + ~4%（1Y 部分与全量重叠），换首屏提前渲染，值得。

## 兼容性

- 生产链路（nginx 直转 8094）与本地 dev（Next rewrites）在两层 gzip 下行为一致。
- `dev 环境后端未启动`：页面 error 态逻辑不变（fetch 失败路径没动）。
- 手动刷新按钮（RefreshButton → update 接口 → refreshKey++）流程不变，仅 fetch 加 `cache: 'reload'`。

## 风险与回滚

| 风险 | 缓解 |
|------|------|
| GZipMiddleware 与 CORS 中间件顺序 | GZip 先 add（外层），验证 preflight/OPTIONS 正常 |
| 改 `def` 后 handler 内多线程并发 query_data | `_QUERY_CACHE_LOCK` 已线程安全；线程池默认 40 线程足够 |
| 分层加载后 ALL 档数据边界（阶段 1 只有 1Y） | ALL 档 loading 占位兜底；不出现半屏数据 |
| localStorage 移除导致离线不可用 | 产品本就在线数据页，可接受；回滚 = revert 前端 commit |

回滚点：后端/nginx 改动与前端改动分两个 commit，可独立 revert。

## 验证环境说明

本地 `backend/macro/data/` 为空、后端未运行。AC1/AC2 实测前需：
1. 本地起后端：`cd backend/macro && python -m uvicorn src.main:app --port 8094`（Windows 下用 `.venv` 若有，否则系统 python）
2. 合成数据：写一次性脚本生成 12 个 CSV 样本（每文件几百行即可验证管道；验证体积压缩效果时造大样本 6000+ 行）
脚本放任务 `research/` 目录，不进主仓库 src。
