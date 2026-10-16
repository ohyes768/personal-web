# 技术设计：RSS 详情页与推送返回详情链接

## 边界与 URL 结构

```
推送端 ──POST /rss/api/rss-relay/post──▶ nginx ──rewrite──▶ 后端 /api/post
                                                    返回 {id, detail_url, ...}
手机/浏览器 ──GET https://web.duomi77.cn:9443/rss/view/{id}──▶ nginx /rss ──▶ 前端 app/view/[id] 页面
                                              页面 ──GET /rss/api/rss-relay/post/{id}──▶ 后端 GET /api/post/{id}
```

- 前端 basePath 已是 `/rss`，`app/view/[id]/page.tsx` 天然映射到 `/rss/view/{id}`，nginx 零改动。
- 后端 API 前缀已有 nginx 转发规则，`GET /api/post/{id}` 自动可用。

## 后端改动（backend/rss-relay）

### 1. store.py — 新增 `find_post(posts_dir, post_id) -> dict | None`

- 先走现有 `_validate_post_id` 拒绝非法 id（防路径穿越）。
- 按 id 定位文件（与 `delete_post` 同样的定位方式），复用 `parse_post` 读取。
- 找不到返回 None → 路由层转 404。

### 2. endpoints.py — 新增 `GET /api/post/{post_id}`

- 响应体与 `GET /api/posts` 列表项一致（id/title/url/source/channel/created_at/content）。
- 非法 id 或不存在 → 404。无鉴权，与 posts/channels 管理接口同边界（README 已声明内网隔离前提；单篇读取属公开阅读性质，id 即凭证）。

### 3. endpoints.py — `create_post` 返回体加 `detail_url`

- 基址取现有 `_CHANNEL_META`（`set_rss_config` 已注入）中的 `channel.link`（app.yaml `app.rss.channel.link: https://web.duomi77.cn:9443/rss`），拼 `{link}/view/{id}`。
- **不新增配置项**：README 已要求"反代路径变化时同步修改此配置与前端公开基址"，复用 `channel.link` 避免第二处配置漂移。
- 向后兼容：仅追加字段。

### 4. 测试

- `GET /api/post/{id}`：存在/不存在/非法 id 三例。
- `POST /api/post` 返回体含 `detail_url` 且格式正确。

## 前端改动（apps/rss-relay）

### 新增 `src/app/view/[id]/page.tsx`

- `'use client'` 组件，`useParams` 取 id，挂载后调 `rssRelayApi`（lib/api 新增 `getPost(id)`，GET `/post/{id}`）。
- 加载态、404 态（"文章不存在或已过期" + 返回列表链接）、错误重试态。
- 正文渲染复用 PostModal 同款：`ReactMarkdown + remarkGfm + .markdown-body`。
- 头部展示标题/source 徽标/时间/原文链接，样式沿用列表页纸感风格（font-serif-cn 标题、ink/paper 色系）。
- 移动端适配：单列、px-4，参照列表页断点写法。
- basePath 注意：页面内请求与链接走 lib/api 现有基址逻辑；`返回列表` 链接用 `/rss`（或 `/`，与现有 header 返回写法一致）。

## 取舍与不做项

- RSS feed item 不加详情页链接（link 保持原文语义）——避免范围蔓延，后续有需要再说。
- 不做列表页 PostCard 跳转详情页入口（现有弹窗阅读已满足；详情页目前仅供推送端回传链接/外发场景）。列表页可选后续加"复制详情链接"按钮，本次不做。
- 不做缓存/CDN 层。

## 兼容与回滚

- 后端接口全部为新增 + 返回体追加字段，无破坏性变更；回滚即还原两文件。
- 前端为新增路由，不影响现有页面；回滚删除目录即可。
- 数据存储格式零变更。
