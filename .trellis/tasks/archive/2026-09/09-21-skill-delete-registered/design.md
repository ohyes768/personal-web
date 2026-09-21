# 技术设计：删除已登记 GitHub Skill

## API 契约

`DELETE /api/skills/{skill_id}`，请求体 `AdminPasswordRequest`（复用，`{password}`），
响应 `DeleteSkillResponse { skill_id: str }`（models.py 新增）。

错误映射（与现有路由风格一致，detail 携带 `{code, message}`）：

| 场景 | 状态码 | code |
|------|--------|------|
| 密码错误 | 401 | （沿用 ensure_admin_password 现状） |
| skill id 非法格式 | 400 | invalid_skill_id |
| registry 中不存在 | 404 | unknown_skill |
| 本地来源条目 | 400 | local_source |
| 任一 target 存在 active 部署 | 409 | skill_active |

## 数据层改动

### registry.py — 新增 `remove(skill_id) -> RegistryFile`

- 加载 → 过滤掉 `s.id == skill_id` → 原子写（复用 `_save`）；
- id 不存在时抛 `RegistryValidationError("unknown skill id: ...")`，route 层转 404；
- 与 `upsert` 对称，`commit_registry_change()` 仍由 route 层调用（与登记路由一致）。

### db.py — SkillStateStore 新增两个方法

- `delete_github_check(skill_id)`：`DELETE FROM github_check WHERE skill_id = ?`；
- `delete_rollback_snapshots(skill_id)`：`DELETE FROM rollback_snapshot WHERE skill_id = ?`（全部 target）。
- `deployment_history` 不动（R5）。无 schema 变更。

## routes.py — 删除路由（放在下架路由之后）

执行顺序（先校验、真源先行、派生数据殿后）：

1. `ensure_admin_password` → `_require_skill_id`；
2. 从 registry `load()` 找条目：不存在 → 404；`source is LOCAL` → 400；
3. `store.list_deployments()` 过滤 `skill_id` 且 `status == "active"`：非空 → 409；
4. `registry.remove(skill_id)` + `commit_registry_change()`（git commit 失败 → 500，与登记路由同样的失败语义，真源以文件为准可手工恢复）；
5. 清理派生数据（均为尽力而为，不再影响响应）：
   - `store.delete_github_check(skill_id)`；`store.delete_rollback_snapshots(skill_id)`；
   - `shutil.rmtree(settings.github_skill_cache_root / skill_id, ignore_errors=True)`，非 ignore 路径用 try/except 打 warning（缓存只是克隆产物，可重登恢复）。

## 前端改动

- `lib/api.ts`：`deleteSkill(skillId, password)` → DELETE + body `{password}`（现有 `request` helper 已支持 method+body，参考 api.ts:162 下架实现）。
- `lib/types.ts`：无需新类型（响应只用 skill_id）。
- `app/page.tsx`：
  - 新增 `pendingDelete: { skillId, skillName } | null` state 与 `performDelete`；
  - 成功后：重新拉取列表 + `setQueue(prev => removeQueueItem(prev, skillId))`（queue.ts 已有）+ notice 提示；
  - 新增一个 ConfirmActionDialog 实例（确认文案：将移除登记条目并删除缓存，不影响已发布目标）。
- `components/SkillPool.tsx`：卡片操作区对 `source === 'github'` 显示"删除"次级按钮，回调 `onDelete(skill)` prop 上抛。

## 兼容性与回滚

- registry.json 结构不变（条目变少），SQLite 无迁移；老数据无需处理。
- **多环境语义**（见 spec/guides/skill-manager-github-cache.md）：registry.json 随源库
  git 同步到所有环境，删除条目是**全局生效**的；缓存目录是环境本地的，本任务的
  缓存清理只影响执行删除的那个环境，其他环境残留的孤儿缓存为无害派生数据（可在
  对应环境手工清理，不做跨环境协调）。
- 回滚：registry.json 在 git 仓库中有历史，可 revert 提交恢复条目；整体改动单 commit 可整体 revert。

## 权衡记录

- 删除是否级联"自动下架"？选择拒绝（409）而非级联：下架是显式动作且有审计，级联会放大误操作半径。
- 缓存目录删除失败是否阻断？选择不阻断（warning）：缓存是可再生的派生数据，阻断会让"删除"卡在一个非关键步骤上。
