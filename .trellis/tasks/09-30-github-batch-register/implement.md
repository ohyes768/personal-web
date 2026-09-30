# 执行计划：合集仓库批量登记（共享缓存 + staging 发布）

> 依据 prd.md / design.md。后端在 `backend/skill-manager/`，前端在
> `apps/skill-manager/`。Windows dev 侧本地验证：`UV_CACHE_DIR=.uvcache uv run pytest`
> 与 `pnpm build`；symlink 完整链路留 Docker/Linux（AC 标注）。

## Phase A 数据模型与存储层

- [ ] A1 `models.py`：`RegistrySkill.shared_paths: list[str] = []` + 模型校验
      （local 必空；github 相对/不穿越/去重排序）；`GithubRegisterItem` /
      `RegisterGithubBatchRequest` / `ScanCandidate` 扩展 / `ScanTopLevelEntry` /
      `ScanResult` 定义
      → verify: `UV_CACHE_DIR=.uvcache uv run pytest tests/ -k model -v`
- [ ] A2 `db.py`：`registry_skill` 加 `shared_paths TEXT NOT NULL DEFAULT '[]'` 列
      迁移（PRAGMA 检测 + ALTER TABLE，幂等）；读写路径同步
      → verify: 既有测试全绿 + 新增迁移用例（旧库文件升级/新库幂等）

## Phase B 共享缓存重构

- [ ] B1 `git_cache.py`：`repo_cache_dir()` 派生（owner__repo，含可逆性注释）；
      `ensure_cached` / `current_revision` / `_check_registered_path_present` /
      `_validated_skill_dir` 全部切换仓库维度路径
      → verify: git_cache 既有测试改基线后全绿
- [ ] B2 `migrate_legacy_cache()`（移动/删多余/双缺失三分支）+ 新测试
      → verify: `uv run pytest tests/test_git_cache.py -v`（新增迁移用例通过）
- [ ] B3 `routes.py` `cache_missing` 判定与 Clone 端点语义切换
      → verify: 卡片缓存判定相关 API 测试

## Phase C staging 发布

- [ ] C1 `publisher.py`：github 分支 staging 组装（tmp 目录 → copytree 本体 +
      shared_paths → 缺失 blocked → 原子 rename → rev 目录清理保留 2 份）；
      `resolve_registry_source` 拆分发布用/plan 用
      → verify: publisher 新旧测试（staging 内容、blocked、rev 清理、local 不变）
- [ ] C2 `routes.py`：`_plan_one` / `_publish_one` / `_planned_revision` 适配
      staging 路径与 revision 口径（full sha 记账，short rev 目录名）
      → verify: plan/publish API 测试
- [ ] C3 lifespan 启动链：DB 列迁移 → `migrate_legacy_cache` → active github
      部署自动重发布（失败记 history error 不阻断）
      → verify: 启动迁移集成用例（旧布局 fixture + active deployment 记录）

## Phase D 扫描增强与批量登记

- [ ] D1 `git_cache._discover_candidates` 返回候选元数据（复用
      `registry._parse_skill_md_frontmatter`，抽到共享位置避免循环依赖）+
      顶层清单 + `referenced_paths` 粗匹配
      → verify: scan 单测（fixture 仓库含多候选 + 根级 tools/）
- [ ] D2 `task_manager.py`：`TaskKind` 加 `register_batch`；
      `start_register_batch()`（仓库级 check_update/ensure_cached 一次 + 逐项
      upsert + 逐项结果快照）+ 测试
- [ ] D3 `routes.py`：`POST /skills/github/batch`（同步预检含批内 id 冲突）；
      单条登记请求体加 `shared_paths` 透传
      → verify: batch 端点测试（202/预检 400/逐项成败快照）

## Phase E 前端

- [ ] E1 `lib/types.ts` / `lib/api.ts`：类型扩展 + `registerGithubBatch()`
- [ ] E2 `RegisterGithubDialog`：checkbox 多选 + 全选/清空；单选手填表单保留、
      多选只读预填列表 + 提示；「随行共享资源」勾选区（referenced_paths 预选）；
      提交分流单/批；ConfirmActionDialog 文案
      → verify: `pnpm build && pnpm lint`；人工走查单选行为与改版前一致
- [ ] E3 批量任务轮询接入（useGithubTask kind 透传）与完成刷新
      → verify: 本地 dev 起前后端，ai-berkshire 扫描→多选 2 项→登记任务 done
      （Windows 本地只验到缓存与登记，不发布）

## Phase F 全量验证与收尾

- [ ] F1 后端全量：`UV_CACHE_DIR=.uvcache uv run pytest tests/ -v` 全绿；
      前端：`pnpm build` / `pnpm lint`
- [ ] F2 Docker/Linux 完整链路（AC）：批量登记 ai-berkshire 2 项 + tools →
      发布 Hermes → 目标目录含 SKILL.md + tools/ → 重复发布 rev 清理 →
      存量升级迁移（旧缓存 + active 部署）
- [ ] F3 spec 更新：`.trellis/spec/guides/skill-manager-github-cache.md` 缓存布局/
      发布模型/迁移章节改写；如前端交互有新约定，补 skill-manager-frontend.md
- [ ] F4 提交：`feat(skill-manager): 合集仓库批量登记——共享缓存与 staging 发布`

## 回滚点

- Phase A/B 独立可回滚（新列旧代码不读；repos/ 布局旧代码不识别但无害）；
- Phase C 落地后回滚需手动恢复 active symlink（重新登记/发布），在 F2 验证通过前
  不部署生产；
- 每阶段独立 commit，按阶段 revert。
