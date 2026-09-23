# 技术设计：宏观 Markdown 报告看板

## 总体数据流

```
a-share/bond impact skill 分析完成
        │
        ▼
push_rss.py ──► RSS Relay POST /rss/api/rss-relay/post   （现状，不变）
        │
        └─► macro POST /api/macro/reports/upload          （新增，X-Upload-Token）
                  │ report_board_service.save_report()
                  ▼
         data/reports/{id}.md  （frontmatter + markdown 正文，原子写）
                  ▲
 apps/macro /macro/reports 看板
   GET /api/macro/reports?source=      列表
   GET /api/macro/reports/{id}         详情
```

## 后端设计（backend/macro）

### 存储：文件系统（无数据库，对齐 macro_signal_service 模式）

- 目录：`settings.macro_report_data_dir`（默认 `./data/reports`，生产 `/app/data/reports`）。
- 每报告一个文件 `{report_id}.md`，结构：

```markdown
---
title: 2026-09-23 A股宏观展望｜偏支撑｜相对利于成长
source: a-share-macro-impact-skill
url: ""
analyzed_at: 2026-09-23
pushed_at: 2026-09-23T18:30:00+08:00
---

（报告正文，即 skill 的 report.md 内容）
```

- `report_id` 生成：`{analyzed_at}-{source_short}-{slug6}`，其中 `slug6 = sha1(source + title)[:8]`。
  - 同日同源同标题 → 同 id → 天然幂等（重推覆盖写相同内容）。
  - 同日重跑但结论变化 → 标题不同 → id 不同 → 新文件，历史版本自然留存（与 RSS「结论变化体现在标题」的设计一致）。
- 幂等判定：`list` 时维护内存索引（dir scan + frontmatter 解析，缓存 + mtime 失效）；`save_report` 先按 `(source, title)` 查索引，命中返回 `duplicate=True` 并跳过写入（内容不覆盖——避免重推时内容漂移，同 id 内容以首次为准）。

> 权衡记录：也可选「同 id 覆盖内容」。选不覆盖，因为重推通常是脚本重试，内容应一致；若内容真变了说明分析变化，应由新标题的新报告承载。

### Service：`src/services/report_board_service.py`

```
ALLOWED_SOURCES = {"a-share-macro-impact-skill", "bond-market-macro-impact-skill"}

class ReportBoardService:
    save_report(title, content, source, url) -> SavedReport      # 白名单校验 / 幂等 / 原子写
    list_reports(source: str | None) -> list[ReportMeta]          # 倒序 by analyzed_at, 再 pushed_at
    get_report(report_id) -> ReportDetail | None
    clear_cache()                                                 # 写入后调用
```

- frontmatter 解析用 `yaml.safe_load`（backend/macro 已有 pyyaml 依赖则直接用，需确认；无则手写轻量 `key: value` 行解析——frontmatter 是我们自家写入的，格式可控）。
- `_atomic_write`：临时文件 + `os.replace`（对齐 `_atomic_write_json` 现有实现）。
- `content` 校验：非空、`len <= 200_000` 字符（防异常 payload），title ≤ 200 字符。
- 文件名安全：report_id 只含 `[0-9a-zA-Z-]`，白名单字符过滤，杜绝路径穿越。

### API（`src/api/routes.py` 追加，复用 `_verify_upload_token` 的模式）

新配置项（`src/config.py`）：
```python
macro_report_data_dir: str = "./data/reports"
macro_report_upload_token: str = ""   # 独立于 MACRO_SIGNAL_UPLOAD_TOKEN，职责清晰
```

```
POST /api/reports/upload   body: {title, content, source, url?}   header: X-Upload-Token
  → 200 {success, data: {report_id, duplicate}}
  → 401 token 错/未配置；400 非法 source / 参数越界
GET /api/reports?source=&limit=    → 200 {success, data: {reports: [ReportMeta], total}}
GET /api/reports/{report_id}       → 200 {success, data: ReportDetail} | 404
```

- 鉴权函数抽公共小工具（与 `_verify_upload_token` 同实现，token 来源不同），不强行合并两 token 为一。
- models.py 新增 `ReportUploadResponse / ReportListResponse / ReportDetailResponse`（`ApiResponse` envelope 风格，对齐现有响应模型）。
- 路由为 `def`（非 async）：文件 IO 小但保持与读盘路由一致的线程池模式。

### nginx / compose

- nginx `/api/macro/* → macro-backend:8094/api/*` 已有，零改动。
- `docker-compose.nas.yml` macro-backend `environment:` 加一行 `MACRO_REPORT_DATA_DIR=/app/data/reports`；部署时另配 `MACRO_REPORT_UPLOAD_TOKEN`。

## Skill 端设计（两个 impact skill 的 scripts/push_rss.py）

两个脚本结构相同（仅常量差异），各自加同一段逻辑：

1. 新增 CLI 参数与常量：
   - `--report-endpoint`，默认 `https://web.duomi77.cn:9443/api/macro/reports/upload`
   - `--report-token`，默认读环境变量 `MACRO_REPORT_UPLOAD_TOKEN`
   - 复用现有 `--insecure`
2. RSS 推送成功（现有 `http_json(...)` 返回）后，追加推送：
   ```python
   payload = {"title": args.title, "content": content, "url": args.url, "source": args.source}
   ```
3. 失败语义：
   - token 缺失 → 打印 warning JSON 字段 `report_push: "skipped_no_token"`，整体返回 0（RSS 已成功）。
   - macro 请求异常/非 200 → `report_push: "failed: <reason>"`，整体返回 0；报告已在本地，重跑整个脚本即可（RSS 侧 duplicate 检测会挡住重复发布，macro 侧幂等）。
   - macro 返回 `duplicate: true` → `report_push: "duplicate"`，正常。
4. 依赖：保持标准库 `urllib`（push_rss.py 现状），不引入 requests。

> 权衡记录：考虑过抽取两 skill 公共脚本。两 skill 目录独立、脚本本就是复制品（仅常量不同），保持现状各自小改，符合「surgical changes」。

## 前端设计（apps/macro）

### 路由与入口

- `src/app/reports/page.tsx`（client component），basePath `/macro` → 访问 `/macro/reports`。
- 主页 header（economic 模块顶部）加「分析报告」链接（`<Link href="/reports">`，Next 自动拼 basePath）。

### 数据层

- `src/lib/api-client.ts` 已有 wrapped envelope 客户端，直接用：
  - `get('/api/macro/reports', { source, limit })`
  - `get('/api/macro/reports/{id}')`
- 新 hook `useReports()`（列表 + source 筛选状态）与 `useReportDetail(id)`（懒加载选中项），放 `src/lib/hooks/reports.ts`。

### 类型（`src/lib/types/reports.ts`）

```ts
interface ReportMeta { reportId: string; title: string; source: string; analyzedAt: string; pushedAt: string; url: string }
interface ReportDetail extends ReportMeta { content: string }
```

### 组件（`src/app/reports/components/`）

| 组件 | 职责 |
|------|------|
| `ReportBoard.tsx` | 页面容器：source 筛选 + 列表/详情两栏状态 |
| `ReportList.tsx` | 列表（含 SourceFilter）；条目=日期+方向词（从标题按 `｜` 拆分渲染） |
| `ReportViewer.tsx` | markdown 渲染 + 移动端返回列表按钮 |

- markdown 渲染：`react-markdown` + `remark-gfm` + `rehype-sanitize`（默认 schema + 允许 `a[href|target]`），外层 `prose` 排版。**sanitize 必须在 rehype 管道内，禁止 `dangerouslySetInnerHTML`**。
- 响应式：`lg:` 以上左列表（固定宽 320px）右详情两栏；以下单栏，选中后详情覆盖，含返回按钮。
- 来源中文名映射：`a-share-macro-impact-skill → A股宏观展望`、`bond-market-macro-impact-skill → 利率债展望`。

### 依赖

`pnpm add react-markdown remark-gfm rehype-sanitize`（apps/macro 新增三个纯前端依赖）。`@tailwindcss/typography` 如未安装则一并加（prose 类）。

## 测试设计

### backend/macro（pytest，贴现有 tests/ 结构）

- `tests/test_report_board_service.py`：save 落盘内容与 frontmatter、幂等（同 source+title 二次 save 不新增文件且 duplicate=True）、白名单 source 400、超长 content 400、list 倒序与 source 筛选、get 未知 id None、report_id 字符安全。
- `tests/test_report_routes.py`：API 层——401（无 token/错 token/未配置）、400（非法 source）、200 上传→列表→详情链路、duplicate 幂等返回、404。

### skill 端

- 两 skill 现有 `tests/` 结构轻量：为 push_rss 的 macro 推送函数补一个纯逻辑单测（mock http，验证 payload 与失败语义映射），不强制。

### 前端

- `pnpm build` 通过 + 浏览器手工验证（dev server 起前后端，curl 灌 2~3 篇样例报告后走查列表/详情/筛选/移动端）。XSS sanitize 用注入样例验证。

## 兼容与回滚

- 纯新增：新接口、新文件目录、新页面；不触碰现有 /signal、/analysis/snapshot、RSS 链路。
- 回滚 = 回退代码 + 删除 compose 一行环境变量；data/reports 目录残留无副作用。
- skill 端回滚 = 不传 token 即恢复旧行为（仅推 RSS）。

## 风险

| 风险 | 缓解 |
|------|------|
| pyyaml 是否已在依赖中 | 实现前确认；无则用受控格式的轻量行解析（frontmatter 自家写入） |
| 自签证书：后端无外呼不受影响；skill → macro 走 `--insecure`/`MACRO_UPLOAD_SSL_VERIFY=0` 既有机制 | 沿用 upload_signal.py 模式 |
| NAS 部署 token 未配置 | 后端 401 拒绝（fail closed）；skill 侧告警跳过不阻塞 RSS |
