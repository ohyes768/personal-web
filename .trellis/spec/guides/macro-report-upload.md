# Macro Report Upload API Contract

> **Purpose**: impact skill 推送 markdown 分析报告到 macro 后端报告看板，以及前端看板消费报告的完整契约。
>
> **Last verified**: 2026-09-23
> **Source files**:
> - `backend/macro/src/api/routes.py`（/api/reports* 三路由）
> - `backend/macro/src/services/report_board_service.py`（落盘/幂等/列表）
> - `backend/macro/src/config.py`（MACRO_REPORT_* 配置）
> - `<skills>/finance-macro/{a-share,bond-market}-macro-impact-skill/scripts/push_rss.py`（推送端）
> - `apps/macro/src/app/reports/`（消费端看板）

---

## 1. 接口（nginx 前缀后对外路径）

```
POST /api/macro/reports/upload        # skill 推送
GET  /api/macro/reports?source=&limit= # 列表（倒序）
GET  /api/macro/reports/{report_id}    # 详情（含 content）
```

nginx `/api/macro/` → 剥前缀 → 后端 `/api/reports*`。dev 模式由 apps/macro 的 Next rewrite 代理到 `MACRO_API_ORIGIN`（默认 localhost:8094）。

## 2. POST /api/reports/upload

Header `X-Upload-Token`：constant-time 比对 `MACRO_REPORT_UPLOAD_TOKEN`。
注意 header 声明为 `Optional`（**故意区别于 signal/upload 的必填**）：必填 header 缺失时 FastAPI 返回 422，无法满足「无 token → 401」的错误语义。

### 2.1 请求体（字段全部 snake_case）

```json
{
  "title": "2026-09-23 A股宏观展望｜偏支撑｜相对利于成长",
  "content": "# 核心判断\n\n...(markdown 全文)...",
  "source": "a-share-macro-impact-skill",
  "url": ""
}
```

| 字段 | 必填 | 约束 |
|------|------|------|
| `title` | ✅ | ≤200 字符；开头 YYYY-MM-DD 作为 analyzed_at，提取不到用推送当日 |
| `content` | ✅ | 非空且 ≤200_000 字符 |
| `source` | ✅ | 白名单：`a-share-macro-impact-skill` / `bond-market-macro-impact-skill` |
| `url` | ❌ | 原文链接，可为空串 |

### 2.2 响应与幂等

```json
{ "success": true, "data": { "report_id": "2026-09-23-a-share-macro-impact-skill-1c1d914a", "duplicate": false } }
```

- `report_id = {analyzed_at}-{source}-{sha1(source+title)[:8]}`，仅 `[0-9a-zA-Z-]`（防路径穿越，路由层 `re.fullmatch` + 服务层 `SAFE_ID_PATTERN` 双重防护）。
- **幂等键 = (source, title)**：命中已有报告 → `duplicate: true`，同 id，**不覆盖内容**（重试场景内容一致；分析变化应由新标题承载）。
- 同日重跑但结论变化 → 标题不同 → 新文件 → 历史版本自然留存。

### 2.3 错误矩阵

| 状态码 | 触发条件 |
|--------|---------|
| 401 | token 未配置（`MACRO_REPORT_UPLOAD_TOKEN`）或错误 |
| 400 | source 不在白名单 / title、content 越界 |
| 422 | body 非 JSON（FastAPI 默认） |

## 3. GET 列表 / 详情

- 列表：`data: {reports: ReportMeta[], total}`，`analyzed_at` 倒序、再 `pushed_at` 倒序；`?source=` 筛选、`?limit=` 默认 100。
- ReportMeta（**snake_case，前端类型必须对齐**）：`report_id / title / source / url / analyzed_at(YYYY-MM-DD) / pushed_at(ISO)`。
- 详情 = ReportMeta + `content`；未知 id → 404。

## 4. 存储（文件系统，无数据库）

```
$MACRO_REPORT_DATA_DIR/           # dev 默认 ./data/reports；生产 /app/data/reports（compose 注入）
└── {report_id}.md                # YAML frontmatter + markdown 正文
```

frontmatter 键：`title / source / url / analyzed_at / pushed_at`（自家写入的 `key: value` 单行格式；**后端无 pyyaml，用手写行解析**，值内换行写入时被单行化——改解析逻辑前先看 `_parse_frontmatter`）。

## 5. skill 推送端约定（两个 impact skill 的 push_rss.py）

1. RSS 推送**成功后**才追加推 macro；RSS 失败路径（strict 阻断 / duplicate 返回 2、3）不触发 macro。
2. 配置：`--report-endpoint`（默认 `https://web.duomi77.cn:9443/api/macro/reports/upload`）、`--report-token`（默认 env `MACRO_REPORT_UPLOAD_TOKEN`，skill 侧放 `finance-macro/.env`）、`--insecure` 同时作用于两端。
3. 结果 JSON 增加 `report_push` 字段，**任何 macro 失败都不改变整体返回码**：
   - `ok` / `duplicate` / `failed: <原因>` / `skipped_no_token`（token 缺失时告警跳过，RSS 仍算成功）。
4. 标准库 urllib 实现，不引入 requests。

## 6. 前端消费约定（apps/macro /macro/reports）

- markdown 渲染必须走 `react-markdown + remark-gfm + rehype-sanitize`，禁止 `dangerouslySetInnerHTML`（内容是 LLM 生成的不可信输入，实测 `<script>`/`<img onerror>`/`javascript:` 链接均被剥离）。
- 元信息头 `url` 渲染前必须过 `safeHref()`（只放行 http(s)，防伪协议）——sanitize 只覆盖 markdown 正文，不覆盖 React 渲染的 href。
- 详情懒加载：选中才请求单篇；切换来源筛选时清空选中项。

## 7. Tests Required

- `backend/macro/tests/test_report_board_service.py`：落盘/frontmatter、幂等不覆盖、白名单、越界拒绝、倒序+筛选、id 字符安全。
- `backend/macro/tests/test_report_routes.py`：401×3、400、上传→列表→详情链路、duplicate、404。
- skill `tests/test_push_report.py`：四种 report_push 状态映射、RSS duplicate 阻断、RSS 失败不触发 macro。

## 8. Wrong vs Correct

### Wrong：读顶层 duplicate（曾写出的 bug）
```python
if macro_response.get("duplicate"):   # 顶层没有该字段，恒为 "ok"
    return "duplicate"
```

### Correct：后端 envelope 是 {success, data:{...}}
```python
data = macro_response.get("data") or {}
if data.get("duplicate"):
    return "duplicate"
```

### Wrong：前端类型定义 camelCase（reportId/analyzedAt）
本项目后端响应一律 snake_case（见 economic.ts 的 dollar_index/usd_cny），前端类型照抄后端字段名，不要自行转换。

## 9. 部署

`docker-compose.nas.yml` macro-backend：`MACRO_REPORT_DATA_DIR=/app/data/reports`、`MACRO_REPORT_UPLOAD_TOKEN`（根 `.env` 提供；skill 侧 `finance-macro/.env` 同步配置同名变量）。nginx/volume 零改动。
