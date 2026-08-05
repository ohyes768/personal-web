# 精简抖音页面：执行计划

## 改动文件清单

| # | 文件 | 类型 |
|---|------|------|
| 1 | `apps/douyin/src/lib/types.ts` | 删类型 |
| 2 | `apps/douyin/src/lib/api.ts` | 删 API |
| 3 | `apps/douyin/src/lib/hooks.ts` | 改 hook |
| 4 | `apps/douyin/src/components/VideoCard.tsx` | 改组件 |
| 5 | `apps/douyin/src/components/VideoModal.tsx` | 改组件 |
| 6 | `apps/douyin/src/app/page.tsx` | 改页面 |

按依赖顺序改：types → api → hooks → 组件 → 页面。

## 执行步骤

### 步骤 1：types.ts — 删类型

删除：
- `export type TabType = 'unread' | 'read';`
- `export interface MarkAsReadDto { is_read: boolean; }`
- `VideoListParams.status` 字段（保留 `page`/`page_size`）

保留：
- `VideoInfo.is_read?: boolean`（后端可能带，不读即可）

### 步骤 2：api.ts — 删 markAsRead

- 删除 `douyinApi.markAsRead` 方法
- 删除 `import type { MarkAsReadDto }`
- `getVideos` 方法去掉 `params.status` 透传
- `VideoListParams` import 同步调整

### 步骤 3：hooks.ts — 改两个 hook

**useDouyinVideos**：
- 签名去掉 `activeTab: TabType` 参数
- 调用 `douyinApi.getVideos()` 时不传 status
- 删 `TabType` 的 import

**useVideoActions**：
- 删 `markAsRead` 回调
- 保留 `deleteRecord`、`deleteWithFile`

### 步骤 4：VideoCard.tsx

- props 删 `activeTab: TabType`、`onMarkAsRead`
- 删整个 `getStatusBadge` 函数
- 标题右侧按钮区：只保留「删除记录」+「删除并取消收藏」两个按钮（始终显示，hover 显隐）
- 删除原「已读 Tab」「未读 Tab」的两个条件分支
- `import type { TabType }` 删除

### 步骤 5：VideoModal.tsx

- props 删 `onMarkAsRead`
- 删 `handleMarkAsRead` 函数
- 操作栏底部简化：始终显示「删除记录」+「删除并取消收藏」+「关闭」（合并两个条件分支为一个）
- **保留** status === 'failed' / 'pending' / 'processing' / 'deleted' 的内容展示（这些不是角标）
- 简化 `useEffect` 里的 `isViewable` 判断（不再依赖 unread/read/completed 分支，但保留语义等价逻辑：只要有 transcript 可能需要拉详情时拉）

### 步骤 6：page.tsx

- 删 `useState<TabType>('unread')`
- 删 `handleTabChange`、`handleMarkAsRead`、`handleModalMarkAsRead`
- `useDouyinVideos()` 无参调用
- `useVideoActions()` 只用 `deleteRecord`、`deleteWithFile`
- 删 `<Tabs>` 组件 + `tabs` 数组
- `VideoCard` props 删 `activeTab`、`onMarkAsRead`
- `VideoModal` props 删 `onMarkAsRead`
- 空状态文案：「暂无未读视频」「暂无已读视频」→「暂无视频」
- 删 `Tabs` 组件 import（如果不再用）

## 验证命令

```bash
# 1. 类型 / 业务引用清理
grep -r "markAsRead\|TabType\|MarkAsReadDto\|activeTab" apps/douyin/src/
# 期望：types.ts 里 is_read?: boolean 字段保留；其他无业务引用

# 2. 单测（如有）
cd apps/douyin && pnpm test 2>/dev/null || true

# 3. lint
cd apps/douyin && pnpm lint

# 4. 构建
cd apps/douyin && pnpm build
```

## 验证清单（手动 / 浏览器）

启动 `pnpm --filter douyin dev`，访问 http://localhost:3004/douyin：

- [ ] 页面只显示一个视频列表（无 Tab）
- [ ] 列表混合 read + unread + failed 状态的视频
- [ ] 卡片标题旁**没有任何角标**
- [ ] 卡片 hover 显示两个删除按钮
- [ ] 点击卡片打开 Modal
- [ ] Modal 内 status='failed' 时显示错误提示
- [ ] Modal 操作栏只有「删除记录」「删除并取消收藏」「关闭」三个按钮
- [ ] 「待处理 (N)」按钮仍然存在且能触发 ASR
- [ ] 「RSS 订阅」按钮仍然存在

## 回滚

```bash
git revert HEAD  # 单 commit
# 或
git reset --hard <previous-commit>  # 危险，需先确认无未提交改动
```

本次改动仅 `apps/douyin/`，无 docker / 部署 / 后端变更，回滚安全。

## 提交策略

单 commit，标题：

```
refactor(douyin): 去掉已读/未读区分，列表统一展示
```

正文：

```
用户改用 RSS 在手机上阅读，前端已读/未读区分失去用途。
- 去掉 Tab 切换，列表统一展示 read+unread+processing+failed
- 删除 markAsRead UI/API/类型
- 删除所有状态角标（卡片视觉更干净）
- 保留删除按钮 + Modal 内状态展示
- 后端不动（保留 status/is_read 字段为死代码）
```
