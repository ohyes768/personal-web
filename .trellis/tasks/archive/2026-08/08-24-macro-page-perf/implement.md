# 执行计划 — 宏观页面访问性能优化

按阶段推进，每阶段末有验证命令 + review gate。后端/nginx（Phase A）与前端（Phase B）分开提交，可独立回滚。

## Phase A — 后端 + nginx（P0）

- [ ] A1. `backend/macro/src/main.py`：`add_middleware(GZipMiddleware, minimum_size=1024)`（注意 add 顺序：在 CORS 之后 add 使其位于外层——实测 OPTIONS/简单 GET 均正常）
- [ ] A2. `backend/macro/src/api/routes.py`：`get_data` 从 `async def` 改 `def`（内部 `data_service.query_data(...)` 调用不变）
- [ ] A3. `routes.py`：`health_check` 从 `async def` 改 `def`
- [ ] A4. `routes.py`：`get_data` 注入 `response: Response`，设 `Cache-Control: public, max-age=300`
- [ ] A5. `nginx/web.conf` http 块加 gzip（gzip on / gzip_types 含 application/json / gzip_min_length 1024 / gzip_comp_level 5）
- [ ] A6. `backend/macro` 跑已有 pytest（确认无回归）

验证（本地起后端 + research/gen_sample_data.py 合成 CSV）：
```bash
# gzip 生效 + 体积对比
curl -s -H "Accept-Encoding: gzip" -o /dev/null -w "%{size_download} %{content_type}\n" "http://localhost:8094/api/data?start_date=2000-01-01"
curl -s -H "Accept-Encoding: identity" -o /dev/null -w "%{size_download}\n" "http://localhost:8094/api/data?start_date=2000-01-01"
# Cache-Control 头
curl -sI "http://localhost:8094/api/data" | grep -i cache-control
# 去阻塞：先触发冷查询（&），300ms 内打 health，响应应 < 300ms
curl -s "http://localhost:8094/api/data?start_date=2000-01-01" > /dev/null &
sleep 0.3 && curl -s -o /dev/null -w "health: %{time_total}s\n" http://localhost:8094/api/health
```

**Review gate A**：AC1/AC2/AC3 本地实测通过 → commit（`perf(macro): 后端 gzip/缓存头/去阻塞 + nginx gzip`）

## Phase B — 前端分层加载（P1）

- [ ] B1. grep `isCached` 的 UI 引用位置，确认移除 localStorage 后展示不破
- [ ] B2. `useFullEconomicData.ts` 重构：
  - 阶段 1 fetch 1Y（首屏渲染）→ 阶段 2 `requestIdleCallback`（兜底 `setTimeout 2000`）fetch 全量
  - `refreshKey > 0`：直接拉全量 + `{cache: 'reload'}`
  - 删除 localStorage 读写（`FULL_DATA_CACHE_KEY`），`isCached` 恒 `false`
  - 新增返回 `isFullRange`
- [ ] B3. ALL 档 loading：timeRange='ALL' 且 `isFullRange=false` 时内容区显示"加载全量数据中"（改 `page.tsx` 或 `useFilteredEconomicData` 消费方，选侵入最小方案）
- [ ] B4. `apps/macro` `pnpm build` 通过
- [ ] B5. `pnpm dev` 手动回归：8 Tab 渲染、时间范围切换（3M/1Y/ALL）、手动刷新流程、清 localStorage 冷启动首屏速度

**Review gate B**：AC4/AC5 验证通过 → commit（`perf(macro): 前端分层加载替代全量首屏+localStorage`）

## Phase C — 收尾

- [ ] C1. spec 更新（若有可沉淀契约：gzip/缓存头约定、线程池 handler 约定）
- [ ] C2. 汇总：告知用户 nginx 配置需在 NAS `nginx -s reload` 生效，前端/后端容器需 rebuild
- [ ] C3. 任务归档

## 回滚点

- Phase A commit：revert 即回到无压缩/阻塞版（无数据格式变化，安全）
- Phase B commit：revert 即回全量首屏 + localStorage（无后端依赖，安全）

## P2 待确认项（默认不做）

- 死代码清理（两个 `useEconomicData`）、`/api/macro/months` 懒加载 —— 用户确认后另开轻量任务
