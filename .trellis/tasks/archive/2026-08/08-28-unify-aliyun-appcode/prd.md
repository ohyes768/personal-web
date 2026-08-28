# PRD: 统一 dividend/macro 阿里云 APPCODE 环境变量为 ALIYUN_API_APPCODE

## 背景

线上 macro 报「获取商品历史数据失败: 未能获取到任何商品数据（阿里云 comkm 返回全空）」，排查中发现同一份阿里云 alirmcom2 appcode 在两个后端有三套管理方式：

| 位置 | 现状 | 问题 |
|------|------|------|
| `backend/dividend-select/src/core/calculator.py:49` | 读 `ALIYUN_API_APPCODE`，**默认值硬编码真实 appcode** | 密钥明文进 git；线上 compose 未注入该变量，实际依赖硬编码值 |
| `backend/dividend-select/src/services/m120_service.py:30` | **纯硬编码** appcode，不读环境变量 | 同上，且环境变量无法覆盖 |
| `backend/macro/src/config.py:25`（`alirmcom_appcode`） | 读 `ALIRMCOM_APPCODE`，默认空 | 与 dividend 变量名不一致，需在 NAS .env 维护两份 |

两个后端调用的是**同一个云市场产品**（alirmcom2 的 comkm），appcode 通用，应当收敛为单一变量名 `ALIYUN_API_APPCODE`（沿用 dividend 旧名，用户已选定）。

## 需求

1. 环境变量统一为 `ALIYUN_API_APPCODE`，全仓库不再出现 `ALIRMCOM_APPCODE`。
2. dividend 侧两处硬编码 appcode 全部清除，一律从环境变量读取，默认值为空串。
3. `backend/dividend-select/docs/data-sources.md` 中 3 处明文 appcode 打码为占位符。
4. `docker-compose.nas.yml`：macro-backend 改注入 `ALIYUN_API_APPCODE`；dividend-backend 新增注入 `ALIYUN_API_APPCODE`。

## 改动范围

**macro（变量改名 + 引用同步）**
- `src/config.py`：`alirmcom_appcode` 字段改名 `aliyun_api_appcode`（`alirmcom_base_url` 保留原名不动，本次不扩大范围）
- `src/services/commodity_service.py:158,159,176`、`src/services/index_service.py:153,154,163`：字段引用与「未配置」日志文案同步改名
- `.env.example:19`、`test_commodity_klines.py:141`

**dividend（清除硬编码）**
- `src/core/calculator.py:49`：默认值 `"404de..."` → `""`
- `src/services/m120_service.py:30`：改为 `os.getenv("ALIYUN_API_APPCODE", "")`（需补 `import os`）
- `docs/data-sources.md:32,47,97`：明文 appcode → `<your_appcode>`

**部署配置**
- `docker-compose.nas.yml:12`（注释）、`:211`（macro 注入改名）、dividend-backend `environment` 段新增一行注入

## 约束与风险

- **部署顺序（关键）**：清除 dividend 硬编码默认值后，NAS 根目录 `.env` 必须**先**把 `ALIRMCOM_APPCODE=xxx` 重命名为 `ALIYUN_API_APPCODE=xxx` 并确认非空，**再**部署新镜像。顺序颠倒会导致 dividend 与 macro 的阿里云数据同时报「未配置」。
- macro 线上 `.env` 原变量名失效，属一次性切换，不做双名兼容（避免长期维护两套名字）。
- `alirmcom_base_url`、dividend 的 `ALIYUN_API_HOST`/`ALIYUN_API_PATH` 命名保持原样。

## 验收标准

1. `grep -r "ALIRMCOM_APPCODE" --exclude-dir=.git .` 零命中（含 .env.example、compose、注释、日志文案）。
2. `grep -r "404de3caed3742ca897e75ddff633066"` 在工作区零命中（git 历史中的残留需另行重置密钥，不在本任务代码范围内，见「后续事项」）。
3. `backend/dividend-select`：`python -m py_compile` 通过相关文件；现有测试（`python -m pytest tests/ -v`）不因本次改动新增失败。
4. `backend/macro`：`python -m py_compile src/config.py src/services/commodity_service.py src/services/index_service.py` 通过；`python test_commodity_klines.py` 通过。
5. 本地以 `ALIYUN_API_APPCODE=xxx` 加载 macro `Settings`，`settings.aliyun_api_appcode` 能读到该值（验证 pydantic 环境变量映射生效）。
6. `docker compose -f docker-compose.nas.yml config` 能正常渲染，dividend-backend 与 macro-backend 的 environment 均含 `ALIYUN_API_APPCODE`。

## 后续事项（不在本任务内）

- 到阿里云市场控制台重置该 appcode（明文已进 git 历史，应视为泄露），重置后只需更新 NAS `.env` 一处。
- 线上报错「comkm 返回全空」的根因确认（订阅/配额/网络），待用户查 NAS 日志。
