# 执行计划：RSS 详情页与推送返回详情链接

按序执行，每步有验证点；后端两步可合并为一次提交单元。

## 1. 后端：store 单篇读取 + GET /api/post/{id}

- [ ] `store.py` 新增 `find_post(posts_dir, post_id)`：`_validate_post_id` → 定位文件 → `parse_post`，找不到返回 None
- [ ] `endpoints.py` 新增 `GET /api/post/{post_id}`，404 语义与列表一致
- [ ] 测试：`tests/` 新增存在/不存在/非法 id 三例
- 验证：`cd backend/rss-relay && uv run pytest tests -q`

## 2. 后端：create_post 返回 detail_url

- [ ] `endpoints.py` `create_post` 返回体加 `detail_url = f"{channel_link}/view/{post_id}"`（channel_link 取自 `_CHANNEL_META` 的 `channel.link`）
- [ ] 测试：断言返回体含 `detail_url` 且以 `/view/{id}` 结尾
- 验证：`uv run pytest tests -q`
- 回滚点：还原 endpoints.py 即可

## 3. 前端：详情页路由

- [ ] `lib/api.ts` 新增 `getPost(id)`
- [ ] 新增 `src/app/view/[id]/page.tsx`：加载态 / 404 态 / 错误重试态 / markdown 正文
- [ ] 移动端 375px 排版检查
- 验证：`cd apps/rss-relay && pnpm build`

## 4. 端到端联调验证

- [ ] 本地起后端（8095）+ 前端（3006），curl POST 推送一篇 → 用返回的 `detail_url`（本地把域名换成 localhost 前端端口）打开，确认标题、来源、时间、markdown 正文、原文链接齐全
- [ ] 访问随机不存在 id → 友好 404 页
- [ ] 浏览器 375px 宽度检查
- 验证命令：
  ```bash
  curl -X POST 'http://localhost:8095/api/post' -H 'Content-Type: application/json' -d '{"title":"详情页验证","content":"# 标题\n\n正文 **markdown**","source":"dev-test"}'
  ```

## 5. 收尾

- [ ] README 路由表补 `GET /api/post/{id}`、POST 返回体说明、详情页 URL
- [ ] 全量回归：`uv run pytest tests -q` + `pnpm build`
- [ ] 审查门：提交前展示 diff，等用户确认后 commit（子 agent 产出新文件必须与引用一起 `git add`）
