# 执行计划：发布链接宿主机路径一致性（同路径挂载）

## Step 1 后端：config.py 校验放宽

- [ ] `targets_mount_root: Path | None = None`；移出 `_MOUNT_ROOT_FIELDS`，
      非 None 时才 resolve+存在性校验；containment 校验仅非 None 时执行；
      模块 docstring 同步
- [ ] `tests/test_config.py` 新增：未传 targets_mount_root → 构造成功、
      target 根可任意布局；既有用例不回归
- 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/test_config.py -v`

## Step 2 后端：link_missing 账实标记

- [ ] `models.py`：`TargetDeployment.link_missing: bool = False`
- [ ] `routes.py` `list_skills`：active 记录按 design 公式计算 link_missing
- [ ] `tests/test_api.py` 新增两例：账本 active + 无链接 → True（无需
      symlink 特权）；账本 active + 链接存在 → False（标 requires_symlink）。
      DeploymentRecord 用 `store.upsert_deployment` 直插
- 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/ -v` 全绿无回归

## Step 3 前端：徽章与类型

- [ ] `types.ts`：`TargetDeployment.link_missing: boolean`
- [ ] `SkillPool.tsx` DeploymentBadge：active + link_missing → amber
      "已发布 · 链接缺失" + tooltip
- 验证：`pnpm lint`、`npx tsc --noEmit`（apps/skill-manager 下）

## Step 4 部署配置与迁移文档

- [ ] `docker-compose.skill-manager.nas.yml`：按 design 改挂载与 env，
      移除 TARGETS_MOUNT_ROOT
- [ ] `deploy/README-fastgithub.md` 或新 `deploy/README-same-path-mounts.md`：
      迁移四步（重建容器 → find 清断链 → 重新发布 → 宿主机验收）
- 验证：`docker compose -f docker-compose.nas.yml -f
  docker-compose.skill-manager.nas.yml config` 本地能渲染（不实际 up）

## Step 5 收尾

- [ ] 2.2 质量检查（后端全量 + 前端 lint/tsc + diff 范围核对）
- [ ] 3.3 spec：`skill-manager-github-cache.md` 补同路径挂载契约段落
- [ ] 3.4 提交（config+tests、前端+后端标记、compose+文档 分 2~3 个
      语义化 commit）

## 回滚点

- Step 1/2/3 独立可 revert；Step 4 回滚需同步恢复 compose 的 /mnt 挂载，
  并按 design「回滚」节重跑 find 清理。

## 浏览器/NAS 实机验收（主会话执行，对照 prd 验收标准）

- 本地：卡片账实标记（造一个 active 记录删链接看徽章）
- NAS：部署后宿主机 `cat ~/.hermes/skills/<id>/SKILL.md`、
  `ls -l` 确认链接 target 为 /home/ohyes768/... 路径
