# Implement — macro 宏观信号 404 修复

按序执行，每步带验证命令。

## Phase A：后端（L1 + L2）

### A1 路由统一
- [ ] `routes.py:2379` `@router.get("/macro/signal")` → `@router.get("/signal")`
- [ ] `routes.py:2400` `@router.get("/macro/months")` → `@router.get("/months")`
- 验证：`grep -n 'router.get("/macro/' backend/macro/src/api/routes.py` 无 signal/months 命中。

### A2 service 写入方法
- [ ] `macro_signal_service.py`：新增白名单常量 `ALLOWED_SKILLS` / `ALLOWED_FILES`、`save_skill_json(skill, file, data) -> Path`（白名单校验 → mkdir → 原子写盘）、`clear_cache()`。
- 验证：`python -c "from src.services.macro_signal_service import MacroSignalService; ..."` import 无错。

### A3 写入路由
- [ ] `routes.py`：新增 Pydantic 入参 model `{skill, file, data}`；新增 `POST /signal/upload`，header 依赖取 `X-Upload-Token`，调 `_verify_upload_token`（constant-time，未配 401）+ `service.save_skill_json`（白名单违例 400）+ `service.clear_cache()`。
- 验证（本地起后端，token 走 env）：
  - 正常推送 → 200 + 落盘文件可见。
  - 错 token → 401；无 token → 401。
  - `skill="../x"` / `file="../../y"` → 400。

### A4 config
- [ ] `config.py`：加 `macro_signal_upload_token: str = ""`（`macro_signal_data_dir` 默认值不变）。
- 验证：本地 `MACRO_SIGNAL_UPLOAD_TOKEN=test ./.venv/bin/uvicorn src.main:app --port 8094` 起服务无报错。

## Phase B：编排 + 密钥（L2 配置）

- [ ] `docker-compose.nas.yml` macro-backend.environment 加 `MACRO_SIGNAL_DATA_DIR=/app/data/macro-signals` 与 `MACRO_SIGNAL_UPLOAD_TOKEN=${MACRO_SIGNAL_UPLOAD_TOKEN:-}`。
- [ ] 根 `.env` 加 `MACRO_SIGNAL_UPLOAD_TOKEN=<openssl rand -hex 16 生成>`（并同步到 NAS 的 .env）。
- 验证：`docker compose -f docker-compose.nas.yml config` 可解析、token 已注入。

## Phase C：前端（L3）

- [ ] `MacroSignalTab.tsx`：加载 effect 开头加 `if (!selectedMonth) { setLoading(false); return; }`；新增 effect `if (!selectedMonth && defaultMonth) setSelectedMonth(defaultMonth)`。
- 验证：`cd apps/macro && pnpm lint && pnpm build` 通过；本地 dev 打开 Tab，Network 面板无 `month=undefined` 请求。

## Phase D：文档

- [ ] `MACRO_SIGNAL_API.md`：说明对外路径 `/api/macro/signal` 不变、后端内部 `/api/signal`（nginx 剥前缀）；新增 `POST /api/macro/signal/upload` 契约 + agent 推送 curl 模板 + token 配置说明。

## Phase E：部署 + 首推 + 线上验证

- [ ] NAS：`git pull` → `docker compose -f docker-compose.nas.yml build --no-cache macro-backend macro-frontend` → `up -d --force-recreate macro-backend macro-frontend`。
- [ ] 首推数据：本地脚本读 `F:/personal-projects/macro-fin-skill/skills/` 下 6 个 JSON，逐个 `curl -X POST https://web.duomi77.cn:9443/api/macro/signal/upload -H "X-Upload-Token:<t>" -H "Content-Type: application/json" -d '{"skill":..,"file":..,"data":..}'`。
- 验证：
  - AC1 `curl 'http://localhost:8094/api/signal?month=2026-05'` → 200。
  - AC5 线上 `curl -sk 'https://web.duomi77.cn:9443/api/macro/signal?month=2026-05' | head -c 300` → 200 + JSON。
  - AC6 浏览器打开宏观信号 Tab 渲染卡片，DevTools 无 `month=undefined`。
