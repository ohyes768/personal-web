# 执行计划：kids 曲目管理

1. 后端 TDD：先在 tests/test_api.py 写用例（RED）
   - GET tracks：正常列表 / 未下载空列表 / 专辑不存在 404
   - DELETE：成功删除同步 job / 删最后一首删 job / 非法文件名 422 / 文件不存在 404 /
     下载中 409 / 路径穿越拒绝
   - queue() partial 可重试
   → 验证：`pytest tests/test_api.py -q` RED
2. 实现 src/main.py：`_album_dir` / `list_tracks` / `delete_track` +
   2 路由 + `DeleteTrackBody` + queue 重试集合加 partial
   → 验证：pytest 全量 GREEN
3. 前端：page.tsx 卡片入口与按钮态、track-manager.tsx 弹窗、globals.css 样式
   → 验证：`pnpm build`（含 tsc）
4. 质量检查：pytest 全量 + 前端构建 + diff 自查（只含本次 hunks）
5. 提交：选择性暂存（main.py 只暂存本次 hunks，避开并行会话改动）；
   spec 新增 track-management.md 并挂到 backend/index.md
6. 归档任务

回滚点：步骤 3 前 backend 可独立成立；每步验证不过不进下一步。
