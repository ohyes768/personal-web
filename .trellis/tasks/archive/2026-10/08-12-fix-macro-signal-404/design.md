# Design — macro 宏观信号 404 修复

## 三层修复总览

| 层 | 改动点 | 文件 |
|---|---|---|
| L1 路由 | `/macro/signal`→`/signal`、`/macro/months`→`/months` | backend/macro/src/api/routes.py |
| L2 数据 | 新增 POST 写入接口 + 配置注入 + 落盘到 macro-data 卷 | routes.py / macro_signal_service.py / config.py / docker-compose.nas.yml / .env |
| L3 前端 | 月份守卫 + 就绪同步 | apps/macro/src/app/modules/economic/components/MacroSignalTab.tsx |

## L1 路由统一

router prefix 已是 `/api`。改装饰器路径：
- `@router.get("/macro/signal")` → `@router.get("/signal")`
- `@router.get("/macro/months")` → `@router.get("/months")`

nginx `location /api/macro/ { rewrite ^/api/macro/(.*)$ /api/$1 break; proxy_pass http://macro_backend; }` 把 `/api/macro/signal` → `/api/signal`，命中。前端不动（仍发 `/api/macro/signal`）。

## L2 数据（agent 推送模式）

### 数据流
```
macro-fin-skill run_all.py（另一仓库，跑各子 skill）
  ↓ 产出 macro_signal.json / risk_data.json
POST /api/macro/signal/upload   （Header X-Upload-Token）
  ↓ nginx 剥前缀 → 后端 /api/signal/upload
后端校验 token + 白名单 → 落盘 /app/data/macro-signals/<skill>/<file>
  ↓ 写后清 service 内存缓存
GET /api/signal   （service 读 /app/data/macro-signals/）
  ↓ 前端 fetch /api/macro/signal
MacroSignalTab 渲染
```

### 写入接口契约
```
POST /api/signal/upload        （router prefix /api；对外经 nginx 为 /api/macro/signal/upload）
Header: X-Upload-Token: <MACRO_SIGNAL_UPLOAD_TOKEN>
Body (JSON):
{
  "skill": "monetary-policy-skill",   # 必须在白名单 6 个之一
  "file":  "macro_signal.json",        # macro_signal.json | risk_data.json
  "data":  { ...该 skill 的原始 JSON... }
}
```
响应：`{success, skill, file, path, bytes}`；401 token 错/未配；400 skill/file 非白名单或 data 非法。

### 白名单（防路径穿越）
- skills：`monetary-policy-skill / money-supply-skill / entity-economy-skill / inflation-skill / exchange-rate-skill / risk-appetite-skill`
- files：`macro_signal.json / risk_data.json`
- 拒绝 `..` / 绝对路径 / 其它值。

### 落盘 + 缓存
- 目录：`{MACRO_SIGNAL_DATA_DIR}/{skill}/{file}`，`mkdir(parents=True, exist_ok=True)`。
- 写后调 `MacroSignalService.clear_cache()` 让 5 分钟缓存立即失效（兑现文档「写入后不需重启」承诺）。
- service 读路径不变（`DIMENSION_FILES` 的 rel_path 已是 `<skill>/macro_signal.json`，完全对齐）。

### 配置
- `config.py`：`macro_signal_data_dir` 默认保留 `F:/personal-projects/macro-fin-skill/skills`（本地），新增 `macro_signal_upload_token: str = ""`。
- `docker-compose.nas.yml` macro-backend.environment 加：
  - `MACRO_SIGNAL_DATA_DIR=/app/data/macro-signals`（macro-data 卷挂 `/app/data`，持久化）
  - `MACRO_SIGNAL_UPLOAD_TOKEN=${MACRO_SIGNAL_UPLOAD_TOKEN:-}`
- 根 `.env` 加 `MACRO_SIGNAL_UPLOAD_TOKEN=<随机串>`（.gitignore 已忽略）。

### token 校验（仿 rss-relay `endpoints.py:48-57`）
- constant-time `hmac.compare_digest`；未配置 token 直接 401（生产必须配，避免误以为已加保护）。

## L3 前端（MacroSignalTab.tsx）

问题：首次 render `availableMonths=[]` → `defaultMonth = sorted[sorted.length-1] = undefined`（行 17）→ `selectedMonth=undefined`（行 19）→ useEffect（行 29）立即 `loadSnapshot(undefined)`。

修复（两处）：
1. 加载 effect 守卫：开头 `if (!selectedMonth) { setLoading(false); return; }`
2. 月份就绪同步 effect：`if (!selectedMonth && defaultMonth) setSelectedMonth(defaultMonth)`（availableMonths 异步到位后补选最近月，触发加载 effect）。

## 与 agent 的边界
- 本仓库交付：后端 POST 接口 + token + 文档（含 curl 模板）。
- macro-fin-skill 仓库（跨仓库，不在本任务）：`run_all.py` 跑完遍历 6 个 JSON，逐个推送。
- 首次上线：手动 curl 推一次本地 6 个 JSON（implement 提供脚本），让线上立即有数据。

## 部署影响
- macro-backend：rebuild（L1+L2 改动）。
- macro-frontend：rebuild（L3 改动）。
- nginx：不动。
- .env：加 token（NAS 的 .env 也要同步加同值）。

## Rollback
- L1 路由改回 `/macro/<x>` + nginx 改回前端 BFF（回到 commit d92db1f 之前）。
- L2 写入接口保留无害（无 agent 调用即空转，可留着）。
