# 精简抖音页面：去掉已读/未读区分

## Goal

用户改用 RSS 服务在手机上订阅阅读抖音文字稿，前端已读/未读区分失去使用价值。本次精简去掉 Tab 切换 + 标记已读 UI/API，列表统一展示所有已识别视频（unread + read + processing + failed）。

## Requirements

### 功能

- 页面只显示一个视频列表，无 Tab 切换
- 列表混合显示 read + unread + processing + failed 状态视频（后端默认过滤 pending/deleted）
- 卡片 hover 显示「删除记录」「删除并取消收藏」两个按钮
- VideoModal 底部操作栏：保留「删除记录」「删除并取消收藏」「关闭」
- 头部右上角保留「待处理 (N)」按钮和 RSS 订阅按钮

### 删除项

- Tab 切换 UI（未读 / 已读）
- 所有状态角标：未读/已读/已删除/识别中/识别失败/待处理
- 「标记已读」按钮（卡片 + Modal）
- `markAsRead` API 调用、`TabType` 类型、`MarkAsReadDto` 类型

### 保留

- 删除记录 / 删除并取消收藏功能
- 视频详情 Modal 内的错误/状态展示（failed/pending/processing/deleted 的内容展示，不是角标）
- 后端不动：`is_read` 字段、`status` 过滤、`/api/aweme/{id}/read` 接口保留为死代码

## Acceptance Criteria

- [ ] 页面只有一个视频列表，无任何 Tab 控件
- [ ] 列表同时包含 unread / read / processing / failed 状态的视频
- [ ] 卡片标题旁没有任何状态角标
- [ ] 卡片 hover 显示两个删除按钮
- [ ] Modal 内有 status='failed' 时显示错误提示（保留）
- [ ] Modal 操作栏只有「删除记录」「删除并取消收藏」「关闭」
- [ ] 头部右上角保留「待处理 (N)」+「RSS 订阅」
- [ ] 空状态文案为「暂无视频」（不分 tab）
- [ ] `grep -r "markAsRead\|TabType\|MarkAsReadDto\|activeTab" apps/douyin/src/` 无业务引用
- [ ] `pnpm --filter douyin lint` 通过
- [ ] `pnpm --filter douyin build` 通过

## Constraints

- 不动后端 `backend/douyin-processor/` 子模块
- 不引入新依赖
- 不动其他前端模块（apps/news、apps/economic、apps/dividend）

## Notes

- 后端默认行为（`endpoints.py` 第 444-445 行）会过滤掉 pending/deleted，前端不传 status 即可获得 read+unread+processing+failed 混合列表
- `VideoInfo.is_read?: boolean` 字段类型在前端保留（后端响应可能带），但不读取
- 删除按钮确认对话框（`confirm`）保留
- 卡片按钮 hover 才显示（`opacity-0 group-hover:opacity-100`）保留
