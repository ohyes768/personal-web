# rss-relay: 加页面删除文章功能

## Goal

在 `apps/rss-relay` 文章列表页加上手动删除入口，用户可一键清理不要的转发文章。

## Background

当前 RSS 中转只有创建（`POST /api/post`）和列表（`GET /api/posts`），没有删除入口。`backend/rss-relay` 是主仓普通目录（非 submodule），前后端改动**一次主仓 commit** 即可。

数据存储：每篇文章一个 `.md` 文件，文件名即 `id`，由 `store.write_post` 写入。

## Scope

### In-Scope

1. **后端**
   - `backend/rss-relay/src/store.py` 加 `delete_post(posts_dir, post_id) -> bool`：删除对应 `.md` 文件，校验 id 防路径穿越。
   - `backend/rss-relay/src/endpoints.py` 加 `DELETE /api/posts/{post_id}`，调用 `delete_post`，返回 `204` 或 `404`。

2. **前端**
   - `apps/rss-relay/src/lib/api-client.ts` 加 `delete(endpoint): Promise<void>` 方法（支持 DELETE method，204 状态不解析 body）。
   - `apps/rss-relay/src/lib/api.ts` 加 `deletePost(id)` 方法（路径 `/rss/api/rss-relay/posts/${encodeURIComponent(id)}`）。
   - `apps/rss-relay/src/components/PostCard.tsx` 右上角加删除按钮（hover 显示），点击 `stopPropagation` 不触发卡片打开，`window.confirm` 二次确认。标题加 `pr-8` 留位置给按钮。
   - `apps/rss-relay/src/app/page.tsx` 加 `handleDelete` 回调：调 API → 成功后 `refresh()` 重拉 → 失败 alert。
   - `apps/rss-relay/src/app/api/rss-relay/[...slug]/route.ts` **加 DELETE 导出**（本地 dev BFF 没它会 405；生产 nginx 不走 BFF，但保留本地开发体验）。
   - 类型无需改（`PostInfo.id` 已存在）。

### Out-of-Scope（明确不做）

- 鉴权 / token（用户决策：删除接口不鉴权）
- 批量删除、撤销、回收站
- 后端日志 / 审计
- `apps/rss-relay` 部署脚本、Dockerfile 改动
- 其他 3 个 submodule（dividend-select / douyin-processor / global-macro-fin）——本次完全不碰

## Constraints

- 后端 `delete_post` 必须用 `posts_dir / f"{post_id}.md"` 解析 + 校验 `post_id` 不含 `/` `\` `..`，否则 400。避免路径穿越。
- 前端删除按钮放在卡片右上角，不破坏卡片整体点击进入详情的现有交互。
- 前端确认弹窗用 `window.confirm`，不引第三方 UI 库。
- 错误兜底：删除失败（404、网络错）必须 alert 用户，不静默吞错。

## Acceptance Criteria

- [ ] 后端：`curl -X DELETE http://localhost:8095/api/posts/<id>` 返回 204；删除后该 `.md` 文件已不存在；不存在的 id 返回 404；包含 `..` 的 id 返回 400
- [ ] 后端：`GET /api/posts` 不再返回被删的 post
- [ ] 前端：列表中 hover 卡片显示右上角删除按钮（× 或垃圾桶图标）
- [ ] 前端：点击删除按钮弹出 `confirm("确定删除「<title>」吗？")`，确认后才发请求
- [ ] 前端：删除成功后该卡片从列表消失，无需刷新
- [ ] 前端：删除失败时弹 alert 报错，列表不变
- [ ] 前后端：`pnpm lint` + `pnpm build` (apps/rss-relay) 通过；后端 Python 语法 `python -m py_compile` 通过
- [ ] 端到端：手动跑一次 `POST → list → DELETE → list`，列表里那条消失

## Risks

- **路径穿越**：用户传入 `id=../../etc/passwd` 可能删除其他文件 → 已通过 store 层校验 + endpoint 层 400 兜底
- **删除进行中的写**：写入和删除并发可能竞态 → 接受（当前 store 也没有锁，单用户场景）

## Verification Plan

```bash
# 后端语法
cd backend/rss-relay && python -m py_compile src/store.py src/endpoints.py

# 前端 lint + build
cd apps/rss-relay && pnpm lint && pnpm build

# 启动后端
cd backend/rss-relay && python -m uvicorn src.main:app --port 8095 &
sleep 2

# 端到端
curl -X POST http://localhost:8095/api/post -H "Content-Type: application/json" \
  -d '{"title":"测试","url":"https://x","source":"test","content":"# test"}'
# 拿到返回的 id
curl http://localhost:8095/api/posts | jq
curl -X DELETE http://localhost:8095/api/posts/<id> -i
curl http://localhost:8095/api/posts | jq  # 该条消失
```

## Notes

- 完成后 commit 信息：`feat(rss-relay): 加页面删除文章功能（后端 DELETE + 前端按钮 + 二次确认）`
- 主仓 dirty 路径 (`backend/dividend-select`) 与本任务无关，commit 时不要 add 它
- 完成后跑 `task.py finish` 清任务并归档