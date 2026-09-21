# 发布链接宿主机路径一致性（同路径挂载）

## Goal

修复 skill-manager 发布 symlink 的命名空间断裂：Publisher 在容器内创建的
symlink 写入的是容器内绝对路径（`/mnt/github-skill-cache/<id>`、
`/mnt/skills-source/<path>`），而 symlink 文件落在宿主机磁盘的
Hermes/OpenClaw 技能目录里。两个 agent 都跑在宿主机上，按宿主机文件系统
解析这些 `/mnt/...` 路径必然断链，agent 侧读不到 SKILL.md。

改用**同路径 bind mount**（容器内外路径完全一致），使 symlink 在容器内
（管理台校验）与宿主机（agent 消费）两侧都能解析。顺带完成卡片
"账实不符"（link_missing）标记。

## 背景与问题

- 部署事实（用户已确认）：Hermes（`~/.hermes/skills/`）与 OpenClaw
  （`~/.openclaw/workspace/skills/`）均跑在 NAS 宿主机；skill-manager
  backend 跑在容器里，挂载 `HOST_PATH → /mnt/*`。
- Publisher（publisher.py:267 `symlink_to(resolved_source)`）写入的
  resolved_source 是容器内路径 → 宿主机断链。
- local 来源 skill 同样中招（链接指向 `/mnt/skills-source/...`）。
- config.py:61-67 的"target 根必须在 targets_mount_root 内"校验是容器
  命名空间产物；同路径挂载后两个 target 根分属不同宿主目录，无共同父级。

## Requirements

1. **同路径挂载**（docker-compose.skill-manager.nas.yml）：四个业务挂载
   改为 `${VAR}:${VAR}`（两侧同为宿主路径），env 根路径直接引用
   `${VAR}`；不再传 `SKILL_MANAGER_TARGETS_MOUNT_ROOT`。
2. **config 校验放宽**：`targets_mount_root` 改为可选（缺省 None）——
   设置了则保留"target 根必须在其内"校验（本地 dev bat 脚本继续兼容），
   未设置则跳过该检查；存在性校验对所有根保留。
3. **卡片账实不符标记**：`GET /api/skills` 对账本 `active` 的部署做目标
   symlink 存在性检查（lstat），缺失 → `TargetDeployment.link_missing=true`；
   前端徽章显示"已发布 · 链接缺失"（amber，带 tooltip 说明）。
4. **迁移指引**：NAS 侧一次性操作文档——重建容器后清理旧断链
   （`find ... -type l ! -exec test -e {} \; -delete`），再对相关 skill
   重新"生成计划 → 发布"生成正确路径的链接。
5. spec 指南补充同路径挂载契约与"为何 symlink 必须全命名空间一致"。

## Constraints

- 不改 Publisher/plan 的任何判定逻辑（同路径后自然正确）；
- 本地 dev（bat 脚本 + `.skill-manager-dev`）行为不变——脚本继续传
  TARGETS_MOUNT_ROOT，走"设置了就校验"分支；
- `.env` 不要求新增变量（复用现有四个 HOST_PATH 变量）。

## Acceptance Criteria

- [ ] `targets_mount_root` 未设置时 Settings 构造成功，含 containment
      校验的现有测试全部不回归；设置时校验行为与原先一致
- [ ] NAS compose 不再引用 `/mnt/*` 业务路径；容器内创建的 symlink
      target 与宿主机路径逐字节一致
- [ ] 宿主机 `cat ~/.hermes/skills/<id>/SKILL.md` 可读（部署后人工验收）
- [ ] 账本 active 但链接被删的 skill，卡片显示"链接缺失"；链接正常时
      不显示；后端测试覆盖两种情况（含 requires_symlink 正例）
- [ ] 后端 pytest 全绿、前端 lint+tsc 通过
- [ ] 迁移步骤写入 deploy 文档（清理断链 find 命令 + 重新发布流程）

## Notes

- state 账本里的 `current_link_target` 历史值是旧容器路径：仅展示字段，
  不参与校验/回滚路径构造（回滚用快照换链接由 Publisher 现场解析），
  重新发布后自然覆盖，无需迁移数据。
