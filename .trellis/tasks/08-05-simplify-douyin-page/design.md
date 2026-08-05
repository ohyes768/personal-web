# 精简抖音页面：技术设计

## 数据流变化

### 改前（双 Tab）

```
page.tsx ─── activeTab (TabType) ─── useDouyinVideos(activeTab)
                                          │
                                          ▼ status=unread|read
                              GET /api/douyin/videos?status={activeTab}
                                          │
                                          ▼ 后端按 status 过滤
                                    单一状态列表（unread 或 read）
```

### 改后（统一列表）

```
page.tsx ─── useDouyinVideos()  （无参数）
                       │
                       ▼ status 不传
              GET /api/douyin/videos（无 status query）
                       │
                       ▼ 后端默认过滤
                 所有非 pending/deleted 的视频
                 （read + unread + processing + failed 混合）
```

## 组件接口变化

### `useDouyinVideos`

**改前**：`useDouyinVideos(activeTab: TabType): { videos, totalCount, loading, refreshing, error, refetch }`

**改后**：`useDouyinVideos(): { videos, totalCount, loading, refreshing, error, refetch }`

### `VideoCard`

**改前 props**：`{ video, activeTab, onClick, onMarkAsRead?, onDeleteRecord?, onDeleteWithFile? }`

**改后 props**：`{ video, onClick, onDeleteRecord?, onDeleteWithFile? }`

- 删 `activeTab` prop
- 删 `onMarkAsRead` prop
- 删整个 `getStatusBadge(status)` 函数（包括所有 7 个 case）
- 卡片右侧按钮区简化为：始终显示「删除记录」+「删除并取消收藏」两个按钮（与原"已读 Tab"分支行为一致）
- 旧未读 Tab 分支里的「标记已读」按钮整体删掉

### `VideoModal`

- props 删 `onMarkAsRead`
- 操作栏底部简化：始终显示「删除记录」+「删除并取消收藏」+「关闭」
- **保留** Modal 内 `status === 'failed' / 'pending' / 'processing' / 'deleted'` 的内容展示（这些是错误/状态内容展示，不是角标）

### `useVideoActions`

**改前**：`{ loading, markAsRead, deleteRecord, deleteWithFile }`

**改后**：`{ loading, deleteRecord, deleteWithFile }`

- 删 `markAsRead` 函数

### `page.tsx`

- 删 `activeTab` state
- 删 `handleTabChange`、`handleMarkAsRead`、`handleModalMarkAsRead` 函数
- 删 `<Tabs>` 组件调用
- 空状态文案改为通用「暂无视频」

## 类型删除清单

| 类型 | 删除原因 |
|------|----------|
| `TabType` | 不再有 Tab |
| `MarkAsReadDto` | 不再调 markAsRead |
| `VideoListParams.status` | 不再按 status 过滤 |
| `VideoListParams` | 不再有任何参数（保留空 interface 或删除） |

**保留**：`VideoInfo.is_read?: boolean` 字段类型保留（后端响应里仍可能带），前端不读它、不基于它渲染。

## API 删除清单

| API | 删除 |
|-----|------|
| `douyinApi.markAsRead` | ✅ 删 |
| `douyinApi.deleteRecord` | 保留 |
| `douyinApi.deleteWithFile` | 保留 |
| `douyinApi.getVideos` | 改：去掉 status 参数透传 |
| `douyinApi.getVideoDetail` | 保留 |
| `douyinApi.getStats` | 保留 |
| `douyinApi.processAsync` | 保留 |

## 后端（不动）

`backend/douyin-processor/src/server/endpoints.py`：

- 第 406-407 行 `status` / `is_read` query 参数保留
- 第 444-445 行 `pending/deleted` 默认过滤保留
- 第 438-449 行状态推断 / 过滤逻辑保留

`/api/aweme/{id}/read` 接口保留（前端不再调用，但保留接口和后端逻辑不破坏）。

## 兼容性 / 风险

| 风险点 | 评估 | 缓解 |
|--------|------|------|
| 列表大小（不再分 tab 可能一次 200+ 条） | page_size 默认 100，UI 仍能 handle | 不在范围内 |
| 后端 `is_read` 字段成为死代码 | 子模块内残留，不影响前端 | CLAUDE.md 规定子模块独立维护，留待后续清理 |
| 旧数据 status='completed' 但 is_read=false 的卡片 | 后端 status 字段推断 is_read，前端不读 is_read 即可 | 不读就不出问题 |
| 删除按钮确认对话框 (`confirm`) | 保留 | 无变化 |
| VideoCard 上按钮 hover 才显示 (`opacity-0 group-hover:opacity-100`) | 保留 | 无变化 |

## Rollback 形状

本次改动仅触及前端 `apps/douyin/`，无构建/部署变更。回滚 = `git revert` 该 commit 即可。
后端不动 → 即使前端回滚到旧版也能正常工作（旧版会重新用 status=unread 过滤）。
