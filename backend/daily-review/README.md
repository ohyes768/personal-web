# daily-review 后端

每日工作回顾服务：汇聚 Windows / NAS 两台机器的 DSH 会话、task-board、git commit 结构化记录，提供今日时间线、项目聚合与 DeepSeek 生成的日报/周报。设计文档见 `docs/daily-review-design.md`。

## 启动

```bash
cd backend/daily-review
uv sync --extra dev
uv run python -m pytest tests/ -v          # 测试
uv run uvicorn src.main:app --host 0.0.0.0 --port 8103   # 端口由 DAILY_REVIEW_PORT 控制
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `DAILY_REVIEW_PORT` | `8103` | 服务端口 |
| `DAILY_REVIEW_HOST` | `0.0.0.0` | 监听地址 |
| `DAILY_REVIEW_DB` | `./data/daily-review.sqlite3` | SQLite 路径 |
| `DAILY_REVIEW_INGEST_TOKEN` | 空 | ingest 鉴权 token；**未配置时 ingest 端点一律 503（fail closed）**，配置后校验 `X-Ingest-Token` 头，不匹配 401 |
| `DAILY_REVIEW_DSH_DIR` | 空 | NAS 本机 `~/.dsh` 只读挂载点；为空时 `/ingest/sync-nas` 返回 503（跳过 NAS 解析） |
| `DEEPSEEK_API_KEY` | 空 | LLM 总结；未配置时 `/reports/generate` 返回 503 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `DEEPSEEK_TIMEOUT` | `120` | LLM 调用超时秒数 |

## API（prefix `/api/review`）

| 路径 | 说明 |
|---|---|
| `POST /ingest/records` | 批量结构化记录 upsert，按 `UNIQUE(machine,kind,external_id)` 幂等，返回 `{received, inserted, skipped}` |
| `POST /ingest/sync-nas` | 解析挂载目录下未处理的 `sessions/*/*/session.v4.jsonl.zstd` 与 `task-board/ledger-v2.json`（文件级游标存于 ingest_log） |
| `GET /today?date=YYYY-MM-DD` | 两机活动合并时间线（按 started_at 排序，含 machine 标注） |
| `GET /projects` | 按 project 聚合：最近活动时间、会话数、commit 数、最近摘要 |
| `GET /reports?type=daily\|weekly` | 报告列表（含摘要首段） |
| `GET /reports/{id}` | 详情：summary_md 全文 + 关联结构化记录 |
| `POST /reports/generate` | body `{report_type, period_start?, period_end?}`；同步调 DeepSeek 生成中文 markdown，失败落 failed 并返回 502 |
| `GET /health` | 健康检查 |

## 安全红线

- NAS 挂载只读，解析器绝不写挂载目录；ledger 一次 open 整读。
- 只存结构化摘要，不保留会话原文；凭据不入库、不入日志。
