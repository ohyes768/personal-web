# Skill Manager 撤回整包仓库软链体系

## Goal

撤回 `3f9d6b5` 引入的"GitHub 仓库整包发布 + 根软链部署"全套设计与代码，恢复逐子 Skill 的旧发布链路；同步清理 NAS 上 pack 相关遗留状态（SQLite 表、`openclaw-pack-discovery` 台账、`openclaw.json.skills.load.extraDirs` 中由 skill-manager 注入的项、`github-skill-cache/repos/` 下的 pack 缓存目录以及当前以包软链形式安装的 skill 链接）。

## Background / Confirmed Facts

- PR `3f9d6b5`（commit hash 3f9d6b5c601cfe8a89eb1b2e19a49bdbc90dedce，PR title "feat(skill-manager): GitHub 仓库整包发布与根软链部署"）净增 2093 行，涉及 36 个文件：新增 `api/packs.py`（153）、`services/packs.py`（521）、`services/openclaw_pack_discovery.py`（210），向后端 `db.py` 加 3 张表（`github_pack`、`legacy_github_pack_member`、`github_pack_history`）+ 12 个方法，`models.py` 新增 `GithubPack` / `PackDeployment` / `PackPlan` / `PackPlanItem` / `PackInstallResult` / `PackInstallItem` / `TargetKey` 等 Pydantic 模型；前端新增 `components/PackWorkspace.tsx` + 测试，把 `apps/skill-manager/src/app/page.tsx` 替换为 PackWorkspace 主导（净 −337 行），新增 `lib/packs.ts` + 测试；nginx `web.conf` 加 `/api/github-packs` 路由，`apps/skill-manager/next.config.js` 加重写规则；部署文档追加"整包直链"段，部署 override 文件 `deploy/docker-compose.skill-packs.yml` 出现。
- 紧跟 PR 的 `96a06ee` chore 提交追加 4 个 pack 专属 pytest 文件（`test_github_packs.py` 326 行、`test_openclaw_pack_discovery.py` 81 行、`test_pack_api.py` 88 行、`test_pack_migration.py` 45 行）与 `deploy/docker-compose.skill-packs.yml`（13 行 OpenClaw 单文件挂载 override）。
- `services/packs.py` 把 'openclaw' 作为硬编码特判至少 6 次（L150 / L186-187 / L252-253 / L285-286 / L366 / L398 / L436），Hermes 未对应适配实现；`openclaw_pack_discovery.py` 全文围绕 `openclaw.json` 的 `skills.load.extraDirs` 维护，注释明示 "Keep one repository symlink while registering its group roots with **OpenClaw**"。Hermes 路径在 pack 体系内"白过"但没有任何运行时差异，说明"openclaw 与 hermes 走整包发布"在实现层是个虚构对称 —— Hermes 本来就通过裸 SKILL.md 递归扫描，包软链对其天然免费工作。
- 老发布链路（`Publisher` + `git_cache.py` 的固定 revision checkout + `app.api.routes` 内的 GitHub scan / register / clone 子资源）仍是工作主路径，所有用户生产部署都建立在它上面；pack 体系只是并行加层，不是取代。
- 后续不依赖 pack 体系的 commits：`2c3c173`、`05a2c4c`、`376d12f`、`e674984`、`1c9400e`、`307c7d0`、`5fbbea6`、`7d77b94`、`31f2e5f`、`36c8f65`、`f67f15f`、`5407e09`。`36c8f65` / `31f2e5f` / `f67f15f` 修改了与 `3f9d6b5` 部分共享的文件，但改动区域不同，回退时局部 3-way merge 应可解。
- NAS 实装用户已确认走过 pack 流程 —— NAS 上必存在以下状态之一或多项：a. SQLite `skill-manager.sqlite3` 中 3 张 pack 表非空记录；b. `~/.openclaw/workspace/skills/` 下存在 `github-<owner>-<repo>-<hash>` 形式的包软链；c. `openclaw.json` 已含 pack 写入的 `extraDirs` 项；d. `~/skill-manager/state/openclaw-pack-discovery.json` 与 `openclaw-pack-discovery-pending.json` 备份存在；e. `~/skill-manager/github-cache/repos/<owner>__<repo>/` 下的 clone 缓存目录。
- `3f9d6b5` 之前的设计任务留存于 `.trellis/tasks/10-13-skill-manager-repo-pack-symlinks/`（`prd.md`、`design.md`、`implement.md`、`verification.md`、`research/findings.md`）—— 这些档案保留作为撤销对象的证据，不动。

## Requirements

### R1 源码回退干净

- 仓库 master 分支 `git revert 3f9d6b5 96a06ee` 后等价的内容：从源码、迁移脚本、测试、部署 override、nginx 路由、前端 Next rewrite、文档段落五个维度移除 pack 体系。
- `apps/skill-manager/src/app/page.tsx` 恢复 `RegisterGithubDialog` / `TaskProgressDialog` 等旧组件的导入，移除 `PackWorkspace` 的 import 与 JSX 渲染；旧发布队列（`PublishQueue` / 旧 `SourceWorkspace`）在文件内重新连线。
- 后端 `services/publisher.py` 仍是 GitHub Skill 发布的唯一入口；pack 引入对它的 3 行补丁也被反向应用。
- `services/git_cache.py` / `services/task_manager.py` / `services/migration.py` / `api/routes.py` 只保留非 pack 范围内的改动（`36c8f65` 等独立 commit 的增量）。
- `db.py` schema 字符串中不含 `github_pack` / `legacy_github_pack_member` / `github_pack_history` 的 CREATE TABLE 语句；`SkillStateStore` 不再拥有 12 个 pack 方法。
- `models.py` 不再 import 或暴露 `GithubPack` / `PackDeployment` / `PackPlan` 等 Pydantic 类型，`TargetKey` 不再包含 `OPENCLAW` / `HERMES` 字面（保留老 `Literal` 表达）。
- `services/packs.py` 与 `services/openclaw_pack_discovery.py` 文件不复存在；`api/packs.py` 不复存在；`apps/skill-manager/src/lib/packs.ts`、`apps/skill-manager/src/lib/packs.test.ts`、`apps/skill-manager/src/components/PackWorkspace.tsx`、`apps/skill-manager/src/components/PackWorkspace.test.ts` 不复存在。
- 前端 `lib/api.ts` / `lib/types.ts` / `lib/useGithubTask.ts` / `next.config.js` 回到 3f9d6b5 之前的状态。

### R2 nginx / 部署文档回退

- `nginx/web.conf` 不存在 `location = /api/github-packs` 与 `location /api/github-packs/{}` 两个 location 块。
- `apps/skill-manager/next.config.js` 的 `rewrites()` 在生产环境下返回 `[]`；dev 环境的 rewrite 列表不包含 `/api/github-packs/:path*`。
- `deploy/docker-compose.skill-packs.yml` 文件被删除。
- `deploy/README-same-path-mounts.md` 末段"整包直链补充（2026-10-13）"段落被反向 —— 主体同路径挂载说明（§"NAS 一次性迁移步骤"、"回滚注意"）保留。
- `docs/skill-manager-nas-setup.md` 末段"GitHub 整包软链（2026-10-13）"段落被反向；其余段落（外部导出、NAS 上线验证清单、ZIP 导出目标管理、回滚、安全要点等）保留。

### R3 单元与集成测试恢复

- `backend/skill-manager/tests/test_github_packs.py`、`test_openclaw_pack_discovery.py`、`test_pack_api.py`、`test_pack_migration.py` 四个文件被删除。
- `pytest tests/` 在 skill-manager 虚拟环境下绿。
- 不删除 `tests/test_deployment_files.py` 等既有的非 pack 测试；`test_deployment_files.py` 涉及的部署文件存在性断言自动随 `docker-compose.skill-packs.yml` 消失而调整。
- 前端 `apps/skill-manager/src/components/PackWorkspace.test.ts` 删除；`vitest` 在 `apps/skill-manager` 下绿。

### R4 NAS 状态清理（脚本化、可回滚）

- 提供一次性 NAS 清理脚本（位置、内容在 design.md 中指定），输入为 NAS 上的 host 路径，输出为可审计的 idempotent 操作：
  - SQLite `skill-manager.sqlite3` 中 `github_pack` / `legacy_github_pack_member` / `github_pack_history` 三张表全部 DROP（`IF EXISTS` 友好）。
  - 删除 `~/skill-manager/state/openclaw-pack-discovery.json` 与 `openclaw-pack-discovery-pending.json`（台账）。
  - 解析 `openclaw.json`，比对台账移除 `skills.load.extraDirs` 中由 skill-manager 注入的项；保留用户手写项；写回前原子替换 + 备份到 `openclaw.json.bak.<ts>`；解析失败立即停手不写。
  - 扫描 `HERMES_SKILLS_ROOT` 与 `OPENCLAW_SKILLS_ROOT`，识别以 `github-` 前缀的包软链（`ls -l` 验证 `->`)；按当前 `legacy_github_pack_member` 映射 + 直链 target 是否仍指向受控 `<repo-cache>/<owner>__<repo>/` 来决策：受控 → 删除；非受控 → 报错不动。
  - `~/skill-manager/github-cache/repos/<owner>__<repo>/` 缓存目录在所有相关包软链已卸载后做"无引用"判定再清理；引用判定方式 = 查询 SQLite `legacy_github_pack_member`（删除前快照）+ 扫描两个目标根是否仍有指向该目录的软链。
  - 任何步骤失败可在 git 回滚代码 + 重跑 NAS 清理之间形成可恢复闭环；脚本自身不引入隐式状态。
- `clean_nas.py` 必须在实施稿中先以 dry-run 模式运行一遍（打印计划、不动盘），用户确认后执行。
- 备份条款：脚本每次写到目标根前对原文件做时间戳备份；SQLite 在 DROP 前做 `.bak` 拷贝。

### R5 数据库 Schema 与 DB 方法留痕

- `db.py` 的 `_COLUMN_MIGRATIONS` 不增删与 pack 相关的项；现有 `deployment.content_hash` 与 `registry_skill.shared_paths` 列迁移保留。
- 不为本次回滚新增 `_COLUMN_MIGRATIONS` 项；recovery 表删除即可，不靠 `state_migration` 永久化记录"曾有 pack"标记（移除后无 fall-through 风险）。
- `db.py` `SkillStateStore` 不暴露 `list_packs` / `upsert_pack` / `persist_pack_conversion` / `migrate_pack_member` / `get_pack_for_skill` / `list_pack_members` / `append_pack_history` / `map_pack_member` 等方法；`migration.py` 与 `publisher.py` 也不再 import 这些符号。

### R6 后台任务与前端交互保留

- `2c3c173` / `05a2c4c` / `376d12f` / `e674984` / `1c9400e` 贡献的 GitHub 扫描 / Clone / 检查更新后台任务链路、`TaskProgressDialog` 轮询、阶段日志、失败恢复全部保留；前端 `useGithubTask` 等 hooks 仍存在。
- `307c7d0` / `5fbbea6` / `7d77b94` / `31f2e5f` / `36c8f65` / `f67f15f` / `5407e09` / `bd21c02` 各自功能（外部导出目标管理、ZIP 导出、扫描候选名称渲染、扫描缓存优先、标签筛选独立成行、返回首页入口）原样保留。
- `RegisterGithubDialog.tsx` 加载并展示 pack 体系之外的旧 multi-select 资源勾选 + 共享路径；`SourceWorkspace.tsx` 重新作为左栏工作台承载注册表 + 仓库登记；`PublishQueue.tsx` 重新作为右栏发布队列承载 Hermes / OpenClaw / ZIP 导出目标的发布选择。

### R7 不增量变更

- 本次回滚不引入新功能、不修改产品行为，**连字符级修复都不做** —— 仅回到 "逐子 skill" 发布链路。
- 不修改 `models.py` 内与 pack 无关的 Pydantic 模型字段。
- 不修改 `db.py` 中非 pack 区域的 schema。
- 不修改既有非 pack 测试 / lint / typecheck 配置。
- 不更新 monorepo 部署脚本（`scripts/deploy-nas.sh`、`scripts/start-skill-manager-dev.bat` 等）的内容；它们不应消费过任何与 pack 相关的环境变量变更（`OPENCLAW_CONFIG_*` 系列同步废弃，因为该挂载仅服务于 `docker-compose.skill-packs.yml`）。

## Acceptance Criteria

- [ ] AC1 / R1, R2：master 分支 `git log` 中两个 revert commit 存在（`revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署` 与 `revert: chore: 补交 skill-manager 测试、部署文件与 rss-relay uv.lock`）；`grep -rE "github_pack|GithubPack|PackService|PackWorkspace|openclaw_pack_discovery|OpenClawPackDiscovery" apps/skill-manager backend/skill-manager nginx deploy docs` 在 `apps/skill-manager/src`、`backend/skill-manager/src`、`backend/skill-manager/tests`、`nginx/web.conf`、`deploy/`、`docs/` 下零结果（`docs/` 残留的引用若为历史 changelog 段允许，但本次新增的"整包软链"段不存在）。
- [ ] AC2 / R1：本地 `pytest tests/`（skill-manager 后端）绿；前端 `pnpm vitest run apps/skill-manager` 绿；移除 4 个 pack 测试文件后无 import 残留（`grep -r "test_github_packs\|test_openclaw_pack_discovery\|test_pack_api\|test_pack_migration" backend/skill-manager` 零结果）。
- [ ] AC3 / R1, R5：`backend/skill-manager/src/db.py` schema 字符串中不含 `CREATE TABLE.*github_pack`、`CREATE TABLE.*legacy_github_pack_member`、`CREATE TABLE.*github_pack_history`；`SkillStateStore` 方法表（`grep -nE "def (list_packs|upsert_pack|persist_pack_conversion|migrate_pack_member|get_pack_for_skill|list_pack_members|append_pack_history|map_pack_member|delete_pack|get_pack)" backend/skill-manager/src/db.py`）零结果。
- [ ] AC4 / R1, R5：`backend/skill-manager/src/services/packs.py`、`backend/skill-manager/src/services/openclaw_pack_discovery.py`、`backend/skill-manager/src/api/packs.py` 三个文件不存在；`backend/skill-manager/src/main.py` 不再 import `packs_router` / `PackService` / `PackError`，lifespan 不再调用 `migrate_legacy` / `recover_conversions`，重新调用 `migrate_legacy_cache` / `republish_active_github_skills`（与 3f9d6b5 之前对齐）。
- [ ] AC5 / R1, R5：`backend/skill-manager/src/models.py` 不再定义 / import pack 专属类型（`GithubPack` / `PackDeployment` / `PackPlan` / `PackPlanItem` / `PackInstallResult` / `PackInstallItem`）；老 `TargetKey` 枚举（OpenClaw / Hermes / Windows 三种 target 的运行时枚举）保留 —— 它在 3f9d6b5 之前就存在，并非 pack 引入。
- [ ] AC6 / R2：`nginx/web.conf` 不存在 `location.*github-packs`；`apps/skill-manager/next.config.js` 实际运行 `next build`（dev 生产双模式）后构建绿；`deploy/docker-compose.skill-packs.yml` 文件不存在。
- [ ] AC7 / R2：`deploy/README-same-path-mounts.md` 末段"整包直链补充"不存在；`docs/skill-manager-nas-setup.md` 末段"GitHub 整包软链（2026-10-13）"不存在；两份文档其余段落内容（外部 ZIP 导出、同路径挂载、NAS 上线验证清单、清理步骤、ZIP 导出目标管理、回滚、安全要点）内容与原版逐字一致（仅移除追加段）。
- [ ] AC8 / R3：移除 4 个 pack 测试文件后，pytest 全集通过；`test_deployment_files.py` 调整后（移除 `docker-compose.skill-packs.yml` 断言，仍保留 `docker-compose.nas.yml` / `docker-compose.skill-manager.nas.yml` / `docker-compose.skill-packs.yml` 不存在断言）通过。
- [ ] AC9 / R4：NAS 清理脚本支持 `--dry-run` 与 `--apply` 两种模式；dry-run 报告"将删除 X 张表 / X 个软链 / X 个 extraDirs 项 / X 个缓存目录"且不落盘；apply 模式按计划执行，每个删除/写操作前先做 `.bak.<ts>` 备份；脚本对异常路径（`openclaw.json` 解析失败、软链指向不受控目录、SQLite 不可写）报错即停不继续后半段。
- [ ] AC10 / R6:前端交互验证：本地起 `pnpm dev`（skill-manager，端口 3008），浏览器 `https://localhost/skills` 应当看到左栏 `SourceWorkspace` 渲染 registry 列表 + GitHub 添加按钮，右栏 `PublishQueue` 渲染 Hermes / OpenClaw / ZIP 导出目标选择；点击 GitHub 添加按钮打开 `RegisterGithubDialog`，按 2026-09-30 的行为勾选共享路径；打开 `TaskProgressDialog` 可见 clone / scan 进度轮询；任何位置不再出现"包"、"Pack"、"整包"按钮或文案。
- [ ] AC11 / R4, R7：清理脚本不引入新文件依赖（仅 `python3` / `sqlite3` 标准库 + `json` / `pathlib` / `argparse`）；脚本放在 `apps/skill-manager/scripts/` 或 `backend/skill-manager/scripts/` 下，由 design.md 指定。

## Constraints / Out of Scope

- 本次只做"撤销"，不评估"为什么不一开始就设计成 pack"。已记录的旧有 PRD / design / verification 留在原任务目录作历史证据。
- 不重写 `Publisher` / `git_cache.py` 的算法；保留 3f9d6b5 之前版本的语义。
- 不修改 `nginx/web.conf` 中 `/skills` 与 `/api/skills` 路由块，仅撤回 pack 路由。
- 不增量升级前端依赖版本，不修改 vitest / eslint / tailwind / next 的配置。
- 不引入新数据库迁移；`db.py` 的 `_COLUMN_MIGRATIONS` 维持现状。
- NAS 脚本必须可重入 —— 二次运行不会重复删除已删项；幂等通过"目标不存在即跳过"实现。
- 旧设计 PRD（R1-R6）要求的 `AC5 / R4`（Linux/NAS 两实际 Agent 均发现并读取示例技能，信任设置和工具路径验证）原本未真机兑现，本次回滚不强制补齐老链路的真实 Agent 验收 —— 老链路验收脚本如还在原任务目录，留作参考，不再为本任务验收项。
- 不动 `services/migration.py` 中与 pack 无关的代码段；不重命名其函数。
- 不修改 `apps/housing-map`、`apps/dividend`、`apps/douyin` 等其他 app 与本次无关的源码。
- `clean_nas.py` 必须在用户当面给到 NAS shell 之前保留 dry-run 默认；不向 CI / cron 注册。

## Open Issues（写到 prd，待 review 时定）

- **OI-1**：撤销是用两个独立 `git revert` commit 还是合成一个 squash reverse？建议两个 commit，符合 git revert 习惯、便于单独退回其中一个。
- **OI-2**：`clean_nas.py` 的最终归宿路径：`backend/skill-manager/scripts/clean_nas.py`（贴近后端）。
- **OI-3**：`test_deployment_files.py` 原本的 pack 部署文件断言是怎么写的？需要读它源码确认，避免撤回之后断言失配但仍误报绿。
- **OI-4**：`96a06ee` 中 `backend/rss-relay/uv.lock`（770 行）与本次回滚无关 —— 应保留还是一起丢掉？建议 rss-relay 的 uv.lock 单独拆出新增一个保留性 revert 后的补充提交；本任务不引入新逻辑，只撤删除测试。
