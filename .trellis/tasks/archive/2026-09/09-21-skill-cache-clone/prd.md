# Skill 管理台缓存丢失 Clone 按钮

## Goal

修复 GitHub 来源 Skill 的"缓存丢失死锁"：已登记进注册表但本环境缓存目录缺失的
GitHub Skill，当前会在发布计划预览中被标为"已阻止（源不可用）"，而界面没有任何
入口能重建缓存，导致该 Skill 永远无法通过界面发布。本任务为这类 Skill 提供
"Clone"按钮，用户先点击重建缓存，再走正常的"生成发布计划 → 确认发布"流程。

## 背景与问题

- GitHub Skill 的发布源在本环境缓存目录 `${GITHUB_SKILL_CACHE_ROOT}/<skill-id>/`，
  只有"UI 登记"（`POST /skills/github`）和"发布执行"两个环节会触发 clone/fetch。
- 注册记录随源库同步到所有环境，但缓存是环境本地的——手工写入 registry.json 的
  Skill（或换环境后）缓存必然缺失。
- 发布计划预览按设计只读（绝不 fetch），源缺失 → 项标 `blocked`；前端只发布
  add/update 项 → `blocked` 项走不到发布 → 发布时的自动 `ensure_cached` 也永远
  不执行 → 死锁。
- 注意：`_ensure_cached_at_recorded_revision` 在无成功检查记录时是 no-op
  （routes.py:445-454），不能作为 Clone 端点的实现基础。

## Requirements

1. 卡片数据：`GET /api/skills` 返回的 GitHub 来源卡片新增 `cache_missing` 字段，
   当 `(GITHUB_SKILL_CACHE_ROOT/<skill-id>/.git)` 不存在时为 `true`；
   本地来源恒为 `false`。
2. 新端点 `POST /api/skills/github/{skill_id}/clone`：
   - 密码保护（与登记/发布/回滚/下架一致，R5）；
   - 语义与登记流程一致：`check_update()`（只读 ls-remote，刷新检查记录）→
     `ensure_cached()`（clone/fetch + 检出远端 revision）；
   - 错误契约复用现有规范：未知 skill → 404；非 GitHub 来源 → 400；
     check/clone 失败 → 400（中文 message）。
3. 前端卡片：`source === 'github' && cache_missing` 时显示"缓存缺失"提示与
   **Clone** 按钮；目标 chips 与"加入队列"禁用（强制先 clone，杜绝死锁）。
4. 点击 Clone 弹出现有密码确认框（ConfirmActionDialog），成功后刷新列表并提示
   "缓存已就绪"；失败在弹框内展示错误。
5. "新增 GitHub Skill"登记流程保持现状（登记 + clone 一体），不改动。

## Constraints

- Clone 只写 `GITHUB_SKILL_CACHE_ROOT` 之内，不触碰源库与目标目录；
- 计划预览保持只读语义不变（"已阻止"仍是安全网，clone 后自然解除）；
- 不改变发布/回滚/下架的任何现有行为。

## Acceptance Criteria

- [ ] 缓存缺失的 GitHub Skill 卡片显示"缓存缺失"提示与 Clone 按钮，
      目标 chips 与"加入队列"同时禁用；
- [ ] 输入正确密码点击 Clone 后，缓存目录被创建（clone 成功），卡片
      `cache_missing` 变为 false，chips 与"加入队列"恢复可用；
- [ ] Clone 后重新"生成发布计划"，该项不再"已阻止"，可正常"确认发布"；
- [ ] 密码错误时 Clone 失败并在弹框内显示错误；
- [ ] 本地来源 Skill 与缓存正常的 GitHub Skill 不显示 Clone 按钮；
- [ ] 后端 pytest 覆盖：clone 成功、未知 skill 404、非 GitHub 来源 400、
      check/clone 失败 400、密码错误；
- [ ] 前端 `pnpm lint` 通过；后端既有测试不回归。

## Notes

- 验证环境：本地 dev（后端 8097 / 前端 3008，缓存根
  `.skill-manager-dev/github-cache`）；注册表中已有缓存缺失样例
  `uzi-skill`、`luopan`（path 均为 "."）。
