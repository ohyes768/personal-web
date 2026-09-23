# 宏观 Markdown 报告看板：接收 skill 推送的分析报告并留存展示

## Goal

宏观 web（backend/macro + apps/macro）新增「分析报告看板」：接收 a-share-macro-impact-skill 与 bond-market-macro-impact-skill 推送的 markdown 分析报告，持久化留存，前端独立页面可浏览全部历史报告。

## Background

- 两个 impact skill 每次分析完成后用 `push_rss.py` 把最终报告推到 RSS Relay（`/rss/api/rss-relay/post`）。RSS 只做订阅分发，macro web 侧无法回看历史。
- macro 后端已有 agent 推送先例：`POST /api/signal/upload`（X-Upload-Token 鉴权 + 白名单 + 原子落盘 + 按月归档），本任务复用该模式。
- 已确认决策：**skill 直推 macro**（非 RSS 拉取）；前端为**独立页面**（非 economic tab）。

## Requirements

### R1 接收接口（backend/macro）

- `POST /api/reports/upload`：接收 `{title, content(markdown), source, url?}`，`X-Upload-Token` header 鉴权（constant-time 校验，未配置拒绝）。
- source 白名单：`a-share-macro-impact-skill`、`bond-market-macro-impact-skill`，违例 400。
- 同 `(source, title)` 重复推送幂等：不重复落盘，返回已有报告 id 与 `duplicate: true`。
- 落盘为 markdown 文件（frontmatter 元数据 + 正文），原子写。

### R2 查询接口（backend/macro）

- `GET /api/reports?source=`：报告列表（id、title、source、分析日期、推送时间、url），按分析日期倒序，支持按 source 筛选。
- `GET /api/reports/{report_id}`：单篇报告详情（含 markdown 正文）。不存在返回 404。
- 对外路径经 nginx 为 `/api/macro/reports*`（nginx 零改动）。

### R3 Skill 推送端（两个 impact skill）

- 两个 `push_rss.py` 各自新增推送目标：RSS 推送成功后，追加 POST 到 macro 报告接口。
- 配置：`MACRO_REPORT_UPLOAD_TOKEN`（缺失则跳过 macro 推送并告警，不阻塞 RSS 流程）、`MACRO_REPORT_UPLOAD_URL`（默认 `https://web.duomi77.cn:9443/api/macro/reports/upload`）、复用 `--insecure`（NAS 自签证书）。
- macro 推送失败不影响 RSS 推送成功状态；报告本地仍在，可重试。

### R4 前端看板（apps/macro）

- 独立页面 `/macro/reports`（`src/app/reports/page.tsx`），主页 header 加入口链接。
- 布局：左侧报告列表（按来源筛选：全部/A股宏观展望/利率债展望；条目显示日期 + 方向词），右侧 markdown 渲染详情；移动端列表/详情切换。
- markdown 渲染：react-markdown + remark-gfm + rehype-sanitize（白名单防 XSS）+ prose 排版。
- 列表懒加载详情：点选后才拉取单篇内容。

### R5 部署配置

- `docker-compose.nas.yml` macro-backend 增加 `MACRO_REPORT_DATA_DIR=/app/data/reports` 环境变量（volume `macro-data` 已挂载 `/app/data`，其余零改动）。
- 生产环境需配置 `MACRO_REPORT_UPLOAD_TOKEN`（与 `MACRO_SIGNAL_UPLOAD_TOKEN` 独立）；skill 侧 `finance-macro/.env` 同步配置。

## Constraints

- macro 后端无数据库，存储沿用文件系统模式（与 macro_signal_service 一致）。
- 不改动 RSS Relay 服务；RSS 推送链路行为不变。
- 不导入 RSS 存量历史报告（后续可选，不在本期）。
- 渲染端必须 sanitize，报告内容来自 LLM 生成，不可信任。

## Acceptance Criteria

- [ ] 用 curl 模拟推送（带 token）→ 200 返回报告 id；重复推送同 (source, title) → `duplicate: true` 且不新增文件。
- [ ] 错误 token / 未配置 token → 401；非法 source → 400。
- [ ] `GET /api/reports` 返回倒序列表；`?source=` 筛选生效；`GET /api/reports/{id}` 返回正文，未知 id 404。
- [ ] 后端 pytest 覆盖：落盘/幂等/白名单/鉴权/列表/详情，全部通过。
- [ ] 两个 skill 的 push_rss.py：RSS 推送成功后自动推送 macro；token 缺失时告警跳过、RSS 仍成功。
- [ ] 前端 `/macro/reports` 可见报告列表，点选渲染 markdown，来源筛选生效；XSS 用例（如 `<script>` 注入内容）被 sanitize。
- [ ] 主页 header 可跳转报告看板。
- [ ] `pnpm build`（apps/macro）与 `pytest`（backend/macro）通过。
