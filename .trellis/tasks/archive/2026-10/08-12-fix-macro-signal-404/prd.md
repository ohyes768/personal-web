# 修复 macro 宏观信号 signal/months 线上 404

## Goal

让 apps/macro 的「宏观信号」Tab 在 NAS 线上可用：`/api/macro/signal` 返回 macro-fin-skill 产出的真实 6 维度数据，前端正确渲染卡片（而非 404 / "该月份无数据"）。

## 背景

线上 `GET /api/macro/signal?month=undefined` 返回 404，排查发现三层叠加缺陷：

1. **路由层**：后端 `@router.get("/macro/signal")`、`/macro/months` 带 `/macro` 前缀（routes.py:2379/2400），与其它端点 `/api/<x>` 不一致；nginx 剥 `/api/macro` 前缀后转发 `/api/signal`，后端无此路由 → 404。
2. **数据层**：`config.py:110` `macro_signal_data_dir` 默认硬编码 Windows 路径 `F:/personal-projects/...`；compose 未注入 `MACRO_SIGNAL_DATA_DIR`，容器里路径不存在 → service 读不到 JSON → snapshot None → 404。
3. **前端层**：`MacroSignalTab` 在 `availableMonths` 未就绪（空数组）时 `selectedMonth=undefined` 仍发请求 → URL 出现 `month=undefined`，即便前两层修好也 `startswith("undefined")` 失败 → 404。

## Requirements

### 功能需求
- R1 后端 signal/months 路由去掉 `/macro` 前缀，与 `/data`、`/health` 等统一为 `/api/<x>`，nginx 现有剥前缀规则即可命中。
- R2 后端新增 **agent 推送写入接口**（POST），接收 macro-fin-skill 产出的 6 个 JSON 并落盘到持久卷；service 读取同一目录。
- R3 写入接口带 token 鉴权（constant-time 校验），token 走环境变量，未配置则拒绝。
- R4 compose 注入 `MACRO_SIGNAL_DATA_DIR`（容器内 macro-data 卷子目录）与 `MACRO_SIGNAL_UPLOAD_TOKEN`。
- R5 前端 `MacroSignalTab`：月份未就绪不发 signal 请求；`availableMonths` 就绪后自动选中最近月份并加载。

### 非功能 / 约束
- C1 nginx 不改（上一次已改 `/api/macro/` 直转后端）。
- C2 数据卷复用现有 `macro-data`（挂 `/app/data`），不新增卷。
- C3 写入接口防路径穿越（skill/file 白名单）。
- C4 本地开发体验不退化：config 默认值保留 Windows 路径，生产靠环境变量覆盖。
- C5 不实现 macro-fin-skill 仓库内的 agent 推送脚本（跨仓库），本任务只交付后端接口 + 对接契约文档。

### Out of Scope
- macro-fin-skill 侧的推送脚本改造（另一仓库）。
- 数据本身的刷新（当前最新数据 2026-05，刷新由 agent 后续跑）。

## Acceptance Criteria

- [ ] AC1 本地 `curl 'http://localhost:8094/api/signal?month=2026-05'` 返回 200 + 6 维度 JSON（而非 404）。
- [ ] AC2 本地 `curl 'http://localhost:8094/api/months'` 返回 `{months:[...]}` 降序。
- [ ] AC3 带 token `POST /api/signal/upload` 写入一个 skill JSON 后，`GET /api/signal` 能读到新数据；无 token 或错 token 返回 401。
- [ ] AC4 路径穿越被拒：`skill="../etc"` 或 `file="../../x"` 返回 400，不写盘。
- [ ] AC5 线上 `https://web.duomi77.cn:9443/api/macro/signal?month=<真实月>` 返回 200 + 数据（agent 首次推送后）。
- [ ] AC6 线上宏观信号 Tab 打开不再出现 `month=undefined` 请求；月份就绪后渲染卡片。
- [ ] AC7 `MACRO_SIGNAL_API.md` 路径示例更新 + 新增 upload 接口契约 + agent 推送 curl 模板。

## Notes

- 后端文档 `MACRO_SIGNAL_API.md` 已有数据契约雏形（`MACRO_SIGNAL_DATA_DIR`、GET 端点），本任务把它从「只读本地文件」升级为「agent 推送写入 + 持久卷」。
- 参考 rss-relay 的 token + POST 落盘模式（`backend/rss-relay/src/endpoints.py:48-57` constant-time 校验）。
