# 宏观页面访问性能优化

## Goal

解决 `/macro` 页面访问慢的问题。当前冷缓存首屏需要等待后端组装 2000 年至今的全量 JSON（估算 3-6MB）、未压缩传输、前端同步解析并写 localStorage，整链路叠加导致首屏数秒级延迟，且慢请求会阻塞后端其他接口。

## 背景（2026-08-24 review 结论）

首屏数据流：`page.tsx` 顶层 `useFullEconomicData` → `GET /api/macro/data?start_date=2000-01-01`（26 年 × 34 序列 ≈ 23 万数据点）→ nginx 剥前缀直转 FastAPI → pandas 同步读 12 个 CSV 组装 → 裸 JSON 返回 → 前端 JSON.parse + localStorage 写入。

## Requirements

按优先级分三档，P0 必须做，P1 强烈建议，P2 可选项（实施前与用户确认）：

### P0 — 传输与阻塞（改动小、收益最大）

1. **开启 gzip 压缩**：`/api/macro/data` 响应 3-6MB 未压缩。nginx（`nginx/web.conf`）无 gzip 配置，FastAPI（`backend/macro/src/main.py`）无 GZipMiddleware。至少启用一处（可两处都开，nginx 优先）。
2. **`get_data` 去阻塞**：`routes.py` 的 `GET /data` 是 `async def` 但直接调用同步 pandas `query_data`（读 12 个 CSV + 全量 reindex/ffill），冷缓存时阻塞事件循环 1-3s，期间 `/signal`、`/months`、`/health` 全部排队。改为线程池执行。
3. **HTTP 缓存头**：`GET /data` 加 `Cache-Control`（数据日更，max-age 300 量级）让浏览器/代理可缓存，避免 1h localStorage TTL 过期后每次全量重拉。

### P1 — 前端请求策略

4. **分层加载**：首屏只需默认 tab（中美利差）+ 3M 范围的数据，当前却等 26 年全量。改为：首屏请求近期数据（如 1Y）立即渲染，`requestIdleCallback` 后台拉全量替换。切换 ALL 档时若全量未就绪需有 loading 态。
5. **localStorage 缓存问题**：几 MB JSON 同步 parse 阻塞主线程、写入常超 5MB 配额静默失败。P0 的 HTTP 缓存生效后评估简化/移除，或迁移到 Cache API。

### P2 — 可选清理（默认不做，除非用户确认）

6. 死代码清理：`apps/macro/src/lib/hooks/useEconomicData.ts` 与 `apps/macro/src/lib/modules/economic/hooks.ts` 两个 `useEconomicData` 已无组件引用。
7. `/api/macro/months` 懒加载：宏观信号 tab 激活时才请求（当前挂载即发）。

## 约束

- 不改变 API 响应结构（`EconomicDataResponse` 字段契约不动），前端各 Tab 过滤逻辑不变
- 后端 CSV 存储、更新流程（n8n /update、fetch history）不动
- 生产链路：浏览器 → nginx（`/api/macro/*` 剥前缀直转 macro-backend:8094）→ FastAPI；本地 dev：Next rewrites 代理到 localhost:8094。两端行为需一致
- nginx 配置改动需在 NAS 上重载 nginx 才生效（提交配置即可，部署由用户操作）

## Acceptance Criteria

- [ ] AC1: `GET /api/macro/data`（经 nginx）响应带 `Content-Encoding: gzip`，传输体积降至未压缩的 ~15% 以内（curl 实测对比）
- [ ] AC2: 后端冷缓存处理 `/data` 期间，并发请求 `/api/health` 不被阻塞（本地起后端实测：先触发冷查询，立刻并发 health，health 响应时间 < 300ms）
- [ ] AC3: `/api/macro/data` 响应含 `Cache-Control` 头，浏览器 TTL 内二次请求不发网络请求或返回 304
- [ ] AC4: 前端首屏（清 localStorage 冷启动）在默认 tab 可见图表，无需等待全量数据返回；ALL 档在全量就绪前有明确 loading 态，就绪后正常渲染
- [ ] AC5: 现有功能回归：8 个 Tab 数据渲染正常、手动刷新按钮流程正常、时间范围切换（3M/6M/1Y/ALL）正常
- [ ] AC6: `pnpm build`（apps/macro）与后端 pytest（若有相关测试）通过
