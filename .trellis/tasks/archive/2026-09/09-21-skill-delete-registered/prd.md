# skill-manager 支持删除已登记的 GitHub Skill

## Goal

管理台目前对已登记的 GitHub Skill "只有添加、没有删除"：条目一旦写入 `registry.json` 就永远留在列表里。本任务补齐删除能力（后端接口 + 前端入口），让误登记或不再需要的 GitHub Skill 可以被移除。

## Requirements

- R1 仅允许删除 `source=github` 的条目。本地 Skill 不提供删除入口（本地条目由源目录扫描自动出现，删源目录即消失）。
- R2 删除是写操作，需管理密码，与发布/下架/登记的密码契约一致（请求体 `{password}`）。
- R3 安全规则：该 skill 在任一 target 存在 `status=active` 的部署记录时拒绝删除（409），提示先下架。
- R4 删除动作的完整语义：
  - 从 `registry.json` 移除条目，并按现有惯例 `git add registry.json` + `git commit`；
  - 清理 SQLite `github_check` 记录；
  - 清理 SQLite `rollback_snapshot` 中该 skill 的全部行；
  - 删除 `GITHUB_SKILL_CACHE_ROOT/{skill_id}` 缓存目录（失败不阻断删除，打 warning 日志）。
- R5 审计：`deployment_history` 为只追加审计表且按 (skill_id, target) 建模，删除动作不写入；删除的审计依赖 registry.json 所在 git 仓库的提交历史。
- R6 前端：GitHub 来源的 skill 卡片提供"删除"按钮 → 密码确认弹窗（复用 ConfirmActionDialog）→ 成功后刷新列表，并同步清空发布队列中该 skill 的排队项。

## Out of Scope

- 不删除"检查 GitHub 更新"与"Clone 重建缓存"功能。
- 不提供本地 Skill 的删除入口。
- 不做任何 SQLite schema 迁移（只新增数据访问方法）。

## Acceptance Criteria

- [ ] 删除未发布的 GitHub skill：registry.json 条目移除且产生 git commit；github_check、rollback_snapshot 清理；缓存目录移除；列表不再显示。
- [ ] 删除已发布（任一 target active）的 GitHub skill：返回 409，registry.json 与状态库均无变化。
- [ ] 对本地来源条目调用删除接口：返回 400。
- [ ] 未知 skill id：返回 404；密码错误：返回 401。
- [ ] 前端：GitHub skill 卡片出现删除按钮，完整走通 确认 → 删除 → 列表刷新 → 队列项清理。
- [ ] `backend/skill-manager` pytest 全绿；`apps/skill-manager` lint 通过。
