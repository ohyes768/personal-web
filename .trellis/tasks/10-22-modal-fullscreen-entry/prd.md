# RSS 弹窗增加全屏阅读入口

## Goal

给 `/rss` 列表页的文章弹窗（PostModal）加一个跳转到公开详情页 `/rss/view/{id}` 的入口，
按钮名「全屏阅读」。补上 10-16 rss-detail-page 任务明确不做的"弹窗 → 详情页入口"。

## Requirements

- PostModal 底部 footer 左侧新增「全屏阅读」按钮：当前窗口导航到 `/rss/view/{post.id}`（原生 `<a>`，与详情页里 `href="/rss"` 同风格，不用 next/link）。
- 「关闭」按钮保持 footer 右侧不变。
- 按钮样式复用 footer 现有按钮样式（`bg-paper-deep hover:bg-rule` 一族）。
- 后端不动（detail 页与 `GET /api/post/{id}` 均已存在）。

## 不做项

- 不做「复制详情链接」按钮（当时设计的另一候选，用户选定跳转方案）。
- 不改列表卡片行为（卡片仍是打开弹窗）。
- 不改 RSS feed item link（保持原文语义）。

## Acceptance Criteria

- [ ] 弹窗点击「全屏阅读」后跳转 `/rss/view/{id}`，详情页正常渲染该文章。
- [ ] 「关闭」与 Esc 行为不变。
- [ ] `apps/rss-relay` lint 与 build 通过。
- [ ] 浏览器预览实际点击验证通过。
