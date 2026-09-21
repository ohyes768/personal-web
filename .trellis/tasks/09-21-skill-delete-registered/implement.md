# 执行计划：删除已登记 GitHub Skill

前置：本任务在 NAS 同路径挂载改动（09-21-skill-host-path-symlinks，工作区未提交）之后执行，
提交时注意分开，不要把两批改动混进一个 commit。

## 步骤

1. **后端 db.py**：新增 `delete_github_check` / `delete_rollback_snapshots`
   → 验证：现有 `UV_CACHE_DIR=.uvcache uv run pytest tests/ -v` 全绿（无回归）。
2. **后端 registry.py**：新增 `remove(skill_id)`（过滤 + 原子写，不存在抛 RegistryValidationError）
   → 验证：pytest 全绿。
3. **后端 models.py + routes.py**：`DeleteSkillResponse`；`DELETE /skills/{skill_id}` 路由
   （顺序见 design.md；404/400/409/500 错误映射）
   → 验证：pytest 全绿。
4. **后端测试 tests/test_api.py**：覆盖 PRD 验收场景
   （成功删除含 git commit 断言、active 拒绝 409、本地 400、未知 404、密码 401、缓存目录被删）
   → 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/test_api.py -v` 全绿。
5. **前端 lib/api.ts**：`deleteSkill(skillId, password)`
   → 验证：`pnpm lint` 通过。
6. **前端 app/page.tsx + components/SkillPool.tsx**：删除按钮（仅 github 来源）、
   ConfirmActionDialog 确认、成功后刷新列表 + `removeQueueItem` 清队列
   → 验证：`pnpm lint` 通过；dev 起服务手测完整链路（按钮 → 确认 → 列表消失 → 队列清理）。
7. **收尾检查**：全量 `uv run pytest tests/ -v` + `pnpm lint` + 确认 diff 无越界改动。

## 验证命令

```bash
cd backend/skill-manager && UV_CACHE_DIR=.uvcache uv run pytest tests/ -v
cd apps/skill-manager && pnpm lint
```

## 回滚点

- 每步独立可回滚；整体完成后单 commit 提交， revert 即回滚。
- registry.json 为 git 真源，误删条目可从 git 历史恢复。

## 审查关口

- 步骤 4 完成后（后端完成）：人工过一遍路由 diff，重点看错误映射与执行顺序。
- 步骤 6 完成后（前端完成）：浏览器实测一轮验收标准，再进入提交。
