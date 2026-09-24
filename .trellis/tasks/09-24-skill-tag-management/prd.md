# skill-manager 单卡标签编辑

## Goal

管理看板每张 skill 卡片支持编辑标签：登记后标签当前不可修改，本任务提供界面上的编辑能力。

## 范围

只做单卡编辑。批量重命名/合并/删除标签为低频运维，本期不做；后续需要时在 service 层加方法 + 端点即可，数据模型不变。

## Requirements

- R1 卡片标签区提供编辑入口（含无标签卡片，显示「添加标签」）；
- R2 编辑弹窗：勾选/取消已有标签（全集从 skill 列表派生）+ 输入新标签名（回车加入，去重、非空、≤40 字符）；保存为该 skill 标签全量替换；
- R3 保存需管理密码（R5），复用 ConfirmActionDialog 密码模式，密码不持久化；
- R4 源目录缺失的本地 skill 也能编辑标签（标签维护不依赖源目录存在）；
- R5 保存成功后卡片、筛选 chips 立即反映新标签。

## 设计要点（实现契约）

- 端点：`PATCH /api/skills/{skill_id}/tags`，请求体 `{password, tags: list[Tag]}`，响应 `{skill_id, tags}`；
- models.py 加 `UpdateSkillTagsRequest` / `UpdateSkillTagsResponse`，Tag 复用现有 1-40 字符约束，校验失败走 Pydantic 默认 422；
- registry.py 加 `update_skill_tags(skill_id, tags)`：`get()` → 未知 id 抛 `RegistryValidationError`（路由映射 404 `unknown_skill`）→ `sorted(set(tags))` 归一化 → **直接 `store.upsert_registry_skill` 落库**（绕过 `upsert()` 的 `_check_path`——store 方法不校验路径，天然满足 R4，db.py 零改动）；
- 前端：api.ts 加 `updateSkillTags(skillId, tags, password)`；新组件 `EditSkillTagsDialog`（勾选 + 新标签输入 + 内聚 ConfirmActionDialog）；`SkillPool` 加 `onEditTags` prop 与铅笔按钮；`page.tsx` 接 state 与 notice。

## Acceptance Criteria

- [ ] 每张卡片（含无标签、含源缺失的本地 skill）可打开编辑弹窗
- [ ] 勾选已有标签 + 新建标签，保存后卡片与筛选 chips 立即更新
- [ ] 密码错误显示可读错误（401），正确后保存成功
- [ ] 未知 skill id 返回 404；空/超 40 字符标签前端拦截
- [ ] 后端 pytest 覆盖 service 方法与端点（401/200/404/422）
- [ ] 前端 `pnpm build && pnpm lint` 通过，现有 vitest 不回归
