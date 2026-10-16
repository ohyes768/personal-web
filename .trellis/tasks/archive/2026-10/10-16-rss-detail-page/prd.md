# RSS 详情页与推送返回详情链接

## Goal

推送端调用 `POST /api/post` 后，返回体直接携带可在浏览器/手机打开的文章详情页 URL；提供公开的文章详情页，渲染 markdown 正文。

现状：`POST /api/post` 只返回 `{id, created_at, file}`（`file` 是容器内路径，不可用）；前端只有一个列表页（PostModal 弹窗），没有可分享的单篇页面。

## Requirements

1. `POST /api/post` 返回体新增 `detail_url` 字段，值为 `https://web.duomi77.cn:9443/rss/view/{id}`（基于现有 `app.rss.channel.link` 配置拼接，不新增配置项）。
2. 新增前端详情页路由 `/rss/view/[id]`（生产完整 URL：`https://web.duomi77.cn:9443/rss/view/{id}`），展示标题、来源、时间、原文链接（如有）、markdown 正文；复用 PostModal 的 ReactMarkdown + remarkGfm + `markdown-body` 样式。
3. 后端新增单篇读取接口 `GET /api/post/{id}`（走现有 nginx `/rss/api/rss-relay/* → /api/*` 转发，无需改 nginx），返回与列表接口一致的文章对象。
4. 文章不存在或已过清理期（15 天）时：接口返回 404；详情页显示友好提示（"文章不存在或已过期"）。

## Constraints

- **鉴权**：详情页与单篇接口不加 token，依赖 id 不可枚举（`{时间戳}-{6位hex随机}`，约 1677 万组合）。理由：链接要在手机/微信/RSS 阅读器里直接点开，带 token 不可行；内容 15 天自动过期，泄露风险窗口有限。**需用户确认此决策**。
- **向后兼容**：`POST /api/post` 只新增字段，现有推送端不受影响；RSS feed 内容不变（item link 仍是原文 URL，不在本次范围）。
- 详情页链接随文章 15 天保留期失效，属预期行为。
- 本地 `http://localhost:8095` 环境下 detail_url 同样按配置的公开基址生成（本地开发拼出生产 URL 属可接受）。

## Acceptance Criteria

- [ ] `curl -X POST .../api/post` 返回体含 `detail_url`，且浏览器打开该 URL 能看到刚推送的文章（标题 + markdown 正文）。
- [ ] 访问不存在的 id：接口 404，详情页显示友好提示而非白屏/报错。
- [ ] 手机宽度（375px）下详情页排版正常可读。
- [ ] `backend/rss-relay` 新增接口与 detail_url 的 pytest 用例通过（`uv run pytest tests -q`）。
- [ ] 前端 `pnpm build` 通过；README 路由表补充新接口与详情页说明。
