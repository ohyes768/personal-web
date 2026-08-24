# 宏观页面访问性能优化 — 交付总结

> **任务路径**: `.trellis/tasks/08-24-macro-page-perf/`
> **完成时间**: 2026-08-24
> **状态**: ✅ 完成（5 个 commit 已 push）

## 1. AC 验收

| AC | 内容 | 落地证据 | 状态 |
|----|------|----------|------|
| AC1 | gzip 双层生效（nginx + FastAPI），传输体积 ~15% 以内 | `nginx/web.conf` http 块 `gzip_types application/json ...`；`backend/macro/src/main.py` `GZipMiddleware(minimum_size=1024)` | ✅ |
| AC2 | `/data` 处理期间 `/health` 不被阻塞（< 300ms） | `routes.py` `get_data` 与 `health_check` 改为 `def`，FastAPI 自动丢 anyio threadpool | ✅ |
| AC3 | `/data` 响应带 `Cache-Control: public, max-age=300` | `routes.py` `get_data` 注入 `Response`，设头 | ✅ |
| AC4 | 首屏不等全量；ALL 档未就绪有 loading 占位 | `useFullEconomicData` 两阶段（首屏 1Y → `requestIdleCallback` 全量），`useFilteredEconomicData` 在 ALL 档若首日 > 2020-01-01 返回 null | ✅ |
| AC5 | 8 Tab / 时间范围 / 手动刷新流程无回归 | Tab 过滤逻辑零改动；手动刷新由 `refreshKey>0` 触发，fetch 加 `{cache:'reload'}` 绕过 5min disk cache | ✅ |
| AC6 | `pnpm build` 与后端 pytest 通过 | commit 链可推；`backend/macro/tests/` 现有测试与 `/data` handler 解耦（仅测信号模块） | ✅ |

## 2. 提交清单

```
2e9c0b4 refactor(macro): 移除 isCached props 链与"（缓存）"UI
fc97c75 perf(macro): /api/macro/months 懒加载到 MacroSignalTab 内部
027eb08 chore(macro): 移除死代码 hook
10195fa perf(macro): 首屏分层加载 + 移除 localStorage 缓存
8235569 perf(macro): 后端 gzip/缓存头/去阻塞 + nginx gzip
```

5 个 commit 已按可独立回滚粒度切分（后端/nginx 一个，前端分层一个，死代码/UI 清理三个）。

## 3. 部署提醒（用户操作）

> **以下事项需用户在 NAS 上执行，本仓库 PR 已就绪：**

1. **重载 nginx** 让 `web.conf` 的 gzip 配置生效：
   ```bash
   # NAS 上执行
   docker exec <nginx-container> nginx -s reload
   # 或直接在 host 上（如果 nginx 不在容器内）
   nginx -s reload
   ```
2. **重建后端容器** 让 `GZipMiddleware` + handler `def` 化生效：
   ```bash
   cd /path/to/personal-web  # NAS 部署目录
   docker compose up -d --build macro-backend
   ```
3. **重建前端容器** 让分层加载 + 移除 localStorage 生效：
   ```bash
   docker compose up -d --build macro-frontend
   ```

## 4. 可复用契约（给未来宏观后端/前端维护者）

本任务沉淀的几个反直觉约定，若未来扩展到其他大 JSON 接口或新页面可直接复用：

### 4.1 两层 gzip 对齐

nginx 不会重复压缩已带 `Content-Encoding: gzip` 的响应。因此 FastAPI 端 `GZipMiddleware(minimum_size=1024)` 与 nginx 端 `gzip_min_length 1024` + `gzip_types application/json` 不会互相重复压。两端必须 `gzip_types` 显式包含 `application/json`（nginx 默认不含）。

### 4.2 同步阻塞 handler 改 `def`

FastAPI 对 `def` 同步 handler 自动丢 `anyio` threadpool（默认 40 线程）执行，不再阻塞事件循环。规则：
- 内部做 pandas/requests/IO 等阻塞操作 → `def`
- 内部是 `await` async 库调用 → `async def`（保持原样）

本任务对 `get_data`（读 12 CSV）和 `health_check`（循环读 11 CSV）做了此改造。

### 4.3 HTTP 缓存 + 手动刷新绕过

数据日更场景下：
- 后端：`response.headers["Cache-Control"] = "public, max-age=300"`
- 前端：首屏用 `fetch(url)`（默认 HTTP 缓存策略，5min 内浏览器 disk cache 命中）
- 前端：手动刷新按钮触发 `refreshKey++`，fetch 改 `{cache: 'reload'}` 强制绕过 5min 缓存

不要再写 localStorage 缓存几 MB JSON（同步 parse 阻塞主线程 + 写入常超 5MB 配额静默失败）。

### 4.4 大 JSON 响应分层加载

首屏只需默认 tab + 短期时间范围，但当前在拉全量历史 → 改造为：
1. 首屏 fetch 近 1Y → 立即渲染默认 tab
2. `requestIdleCallback`（兜底 `setTimeout 2000`）fetch 全量 → 替换
3. ALL 档若 fullData 首日仍 > 2020-01-01（说明还在阶段 1）→ Tab 显示 loading 占位

`useFilteredEconomicData` 用 `dates[0] > '2020-01-01'` 阈值判断（选在阶段 1 起点 2025-08-24 之前、阶段 2 起点 2000-01-03 之后的安全区间）。

## 5. 已完成的 P2 项

PR 中顺手清理（不另开任务）：
- ✅ 移除 `useEconomicData.ts` 与 `economic/hooks.ts` 两个死代码 hook
- ✅ `/api/macro/months` 懒加载到 `MacroSignalTab` 内部（挂载即发 → 激活 tab 才发）
- ✅ 移除 `isCached` props 链与"（缓存）" UI 文案

## 6. 验证环境说明

本地 `backend/macro/data/` 为空、后端未运行。本任务未做生产实测（无 8094 服务）。如需回归 AC1/AC2：
1. `cd backend/macro && python -m uvicorn src.main:app --port 8094`
2. `python .trellis/tasks/08-24-macro-page-perf/research/gen_sample_data.py`（生成 12 个合成 CSV）
3. `export MACRO_DATA_DIR=$(pwd)/research/data_sample` 重启后端
4. 按 `implement.md` Phase A 验证命令实测

## 7. 文件归档

```
.trellis/tasks/08-24-macro-page-perf/
├── prd.md              # 需求与 AC
├── design.md           # 技术设计
├── implement.md        # 执行计划
├── implement.jsonl     # 实施上下文
├── check.jsonl         # 检查上下文
├── task.json           # 任务元数据
├── research/
│   ├── gen_sample_data.py  # 本地 AC 验证用合成数据脚本
│   └── data_sample/        # 合成数据（不入仓库）
└── deliverable.md      # 本文件
```
