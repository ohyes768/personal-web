# 技术设计：发布链接宿主机路径一致性（同路径挂载）

## 核心思路

symlink 的 target 是写入时的字面路径，跨命名空间必然断。与其让"消费方"
（宿主机 agent）适配容器路径，不如让**容器与宿主机共享同一路径视图**：
bind mount 两侧用同一个宿主路径。此后 Publisher 写什么路径，宿主机就是
什么路径，管理台容器内的校验（resolve/受控根判断）与宿主机解析天然一致。

## 变更一：NAS compose（docker-compose.skill-manager.nas.yml）

```yaml
    volumes:
      - ${SKILLS_SOURCE_HOST_PATH}:${SKILLS_SOURCE_HOST_PATH}:rw
      - ${GITHUB_SKILL_CACHE_HOST_PATH}:${GITHUB_SKILL_CACHE_HOST_PATH}:rw
      - ${OPENCLAW_SKILLS_HOST_PATH}:${OPENCLAW_SKILLS_HOST_PATH}:rw
      - ${HERMES_SKILLS_HOST_PATH}:${HERMES_SKILLS_HOST_PATH}:rw
      - skill-manager-state:/app/state
      - ./deploy/fastgithub-ca.pem:/etc/ssl/fastgithub-ca.pem:ro
    environment:
      - SKILLS_SOURCE_ROOT=${SKILLS_SOURCE_HOST_PATH}
      - GITHUB_SKILL_CACHE_ROOT=${GITHUB_SKILL_CACHE_HOST_PATH}
      - OPENCLAW_SKILLS_ROOT=${OPENCLAW_SKILLS_HOST_PATH}
      - HERMES_SKILLS_ROOT=${HERMES_SKILLS_HOST_PATH}
      # SKILL_MANAGER_TARGETS_MOUNT_ROOT 不再传入：两个 target 根分属
      # 不同宿主目录，无共同挂载父级；边界改由 bind mount 白名单保证
```

- CA 证书与 state 挂载不变（/etc/ssl、/app/state 是容器私有路径，
  不出现在任何 symlink 里）。
- `.env` 零改动（复用现有变量；值尾斜杠由 config 的 resolve 归一）。
- 安全边界迁移说明：原 `/mnt/targets` 包含性校验的意图是限制容器可见
  文件系统；同路径挂载后边界 = bind mount 白名单本身（容器只挂了这几个
  目录），由 compose 声明，不再需要应用层重复校验。

## 变更二：config.py

```python
targets_mount_root: Path | None = None   # Field alias 不变
```

- `_MOUNT_ROOT_FIELDS` 移除 `targets_mount_root`，改为：**仅当该字段
  非 None 时**做 resolve + 存在性校验；
- containment 校验（openclaw/hermes 根 ⊆ targets_mount_root）仅当非
  None 时执行；
- 模块 docstring 同步更新。

兼容性：本地 dev bat 脚本继续传 `SKILL_MANAGER_TARGETS_MOUNT_ROOT` →
走"设置了就校验"分支，行为不变；既有测试（test_config.py:35 等）全部
传了该字段，不回归。新增用例：不传 → 构造成功且 target 根可任意布局。

## 变更三：卡片账实不符标记

后端（与上游 clone 任务同一模式）：

- `TargetDeployment` 增 `link_missing: bool = False`；
- `list_skills`（已注入 Settings）：对 `status == "active"` 的记录计算
  `not (_target_root(settings, TargetKey(record.target)) / record.skill_id).is_symlink()`。
  纯 lstat，每条一次，零子进程。removed 记录不出徽章，不检查。

前端：

- `types.ts`：`TargetDeployment.link_missing: boolean`（snake_case 直传）；
- `SkillPool.tsx` `DeploymentBadge`：active 且 link_missing → amber 徽章
  "已发布 · 链接缺失"，tooltip 说明"账本记录已发布，但目标目录链接已
  不存在（可能被手动删除）；生成发布计划会按实况判定动作"。

## 迁移（NAS 一次性）

1. 同步代码 → `docker compose ... up -d --build skill-manager-backend`；
2. 清理旧断链（只删失效链接，实体目录不受影响）：
   ```bash
   find ~/.hermes/skills -maxdepth 1 -type l ! -exec test -e {} \; -delete
   find ~/.openclaw/workspace/skills -maxdepth 1 -type l ! -exec test -e {} \; -delete
   ```
3. 界面重新"生成计划 → 发布"相关 skill（链接按新路径原子重建）；
4. 宿主机验收：`cat ~/.hermes/skills/<id>/SKILL.md`。

不清理断链直接走 plan 也可自愈地发现：旧链接 resolve 不到受控根 →
blocked"现有链接指向受控目录之外"（安全语义照旧），但无法经界面修复，
所以迁移文档以 find 删除为标准步骤。

## 权衡与回滚

- 备选（agent 容器化挂相同 /mnt、发布改拷贝）见任务讨论，均因运维成本
  或丢失原子 symlink 语义否决；
- 回滚：revert 两个 commit（config+compose、账实标记）+ compose 恢复
  /mnt 挂载重建即可；已按新路径发布的链接在回滚后容器内不可解析（plan
  会 blocked），需再走一次迁移的 find 清理——文档注明。

## 安全复核

- 容器可见面由 compose 挂载白名单决定，未扩大（同样的四个目录，只是
  路径不同）；
- Publisher 的受控根校验（`_inside_controlled_roots`）继续生效——同路径
  后源根/缓存根的值即宿主路径，宿主机手动链接到别处仍会被 plan blocked。
