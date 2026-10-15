# 执行计划：Skill Manager Pack 体系撤销

## 执行顺序总览

```
阶段 1 — 源码撤销（revert + 冲突解决）       verify: 后端测试 + 前端构建
阶段 2 — 改动 test_deployment_files.py        verify: pytest 通过
阶段 3 — 写 clean_nas.py 脚本                   verify: --help、--dry-run 零落盘
阶段 4 — 创建 NAS 现场清理执行文档               verify: 与 OI-2 路径对齐
阶段 5 — 自检 + 提交两个 revert commit + NAS 脚本 commit
```

实施期间不再触发其它 commit 改动；`git status` 在每个阶段结束应为 clean（除阶段 5 自身的产出）。

## 阶段 1 — 源码撤销（`git revert --no-commit`）

**目的**：把 `3f9d6b5` 与 `96a06ee` 两个 commit 完整反向应用到工作区，不写 commit message。

### 步骤 1.1 准备 revert 上下文

```
git checkout master
git pull --ff-only origin master
git status
```

期望：工作区 clean。如 dirty，停手。

### 步骤 1.2 反向应用（不写 commit）

```
git revert --no-commit 3f9d6b5
# 此时若有冲突，git 会进入 unmerged 状态
git revert --no-commit 96a06ee
# 此时状态：a) clean，b) 有冲突需要解
```

预期：`git status` 显示若干 `UU`（冲突）状态文件。按 §2.3 预案逐个解。

### 步骤 1.3 冲突解决（按 design §2.3）

按以下顺序处理冲突文件。每解一个冲突文件后用 `git add <file>` 加入 staged：

```
git status                              # 列出冲突清单
```

1. `apps/skill-manager/src/app/page.tsx`（如冲突）—— 删 `PackWorkspace` import 与 JSX 块，保留旧组件渲染。
2. `apps/skill-manager/src/components/TaskProgressDialog.tsx` —— 删 `3f9d6b5` 加的 pack 分支（如有），保留 1c9400e 等的后台轮询逻辑。
3. `apps/skill-manager/src/components/TaskProgressDialog.test.ts` —— 删 `3f9d6b5` 加的 pack 测试用例，保留后台轮询测试。
4. `apps/skill-manager/src/components/ConfirmActionDialog.tsx` —— revert −8 后大概率无冲突。
5. `apps/skill-manager/src/lib/types.ts` —— 删 pack union 与枚举，保留 export types。
6. `apps/skill-manager/src/lib/api.ts` —— 删 pack API 客户端代码。
7. `apps/skill-manager/src/lib/useGithubTask.ts` —— 删 pack 路径分支。
8. `apps/skill-manager/next.config.js` —— revert 应自动；如冲突，按 §2.1 删 `{ source: '/api/github-packs/:path*', ... }`。
9. `nginx/web.conf` —— revert 应自动；如冲突，按 §2.1 删两个 location 块。
10. `backend/skill-manager/src/api/routes.py` —— 保留 export_target 路由、cache 优先逻辑；删 pack 路由 mount 与 `/api/github-packs/*` 视图。
11. `backend/skill-manager/src/main.py` —— revert 应自动；如冲突，删 packs_router import + app.include_router(packs_router) + PackError exception handler；恢复 `migrate_legacy_cache` + `republish_active_github_skills` 调用。
12. `backend/skill-manager/src/db.py` —— revert 应自动；如冲突，仅删与 pack 相关的 schema SQL 与方法。
13. `backend/skill-manager/src/models.py` —— 删 pack models 及其 import；保留 export_target models。
14. `backend/skill-manager/src/services/task_manager.py` —— 通常无冲突；如冲突按区域判断。
15. `backend/skill-manager/src/services/git_cache.py` —— 通常无冲突。
16. `backend/skill-manager/src/services/migration.py` —— 删 pack import，按需保留 export_target 迁移。
17. `backend/skill-manager/src/services/publisher.py` —— 通常无冲突。
18. `backend/skill-manager/src/config.py` —— 通常无冲突（仅 +2）。
19. `backend/skill-manager/tests/test_deployment_files.py` —— 删 `docker-compose.skill-packs.yml` 断言。

每个文件解决后：
```
git add <file>
git status
```

### 步骤 1.4 验证 revert 后工作区

```
git status
# 期望：除 revert 修改的文件外，没有遗留冲突标记
```

```
git diff --cached --stat | head -50
# 期望：变更与 3f9d6b5 + 96a06ee 的"反向 1:1"匹配，净行数约为 −2093 + −270 ≈ −2363（4 个 pack 测试 + docker-compose.skill-packs.yml ≈ 540 + 13 = 553）
```

### 步骤 1.5 触发后端测试

```
cd backend/skill-manager
./.venv/bin/python -m pytest tests/ -v 2>&1 | tee /tmp/pytest-after-revert.log
# 期望：绿。如 fail，按失败 stacktrace 修复。
```

针对失败模式分类：
- `test_github_packs.py / test_openclaw_pack_discovery.py / test_pack_api.py / test_pack_migration.py`：这些文件应被 `revert 96a06ee` 删除；如未删，手动 `git rm`。
- `test_deployment_files.py` 的部署文件断言：可能仍在引用已删除的 pack compose —— 调整这些断言至"该 compose 不存在"。

### 步骤 1.6 触发前端测试与构建

```
cd apps/skill-manager
pnpm vitest run 2>&1 | tee /tmp/vitest-after-revert.log
pnpm tsc --noEmit 2>&1 | tee /tmp/tsc-after-revert.log
pnpm next build 2>&1 | tee /tmp/build-after-revert.log
NODE_ENV=production pnpm next build 2>&1 | tee /tmp/build-prod-after-revert.log
pnpm lint 2>&1 | tee /tmp/lint-after-revert.log
```

期望：全部绿。
常见失败模式：
- `tsc --noEmit` 报"Cannot find module '@/lib/packs'" 或类似 → 删 imports。
- `vitest` 报"PackWorkspace is not defined" → 删所有 PackWorkspace 测试引用。
- `next build` 报 missing route `/api/github-packs` → next.config.js 残留；按 §2.1 删除。

### 步骤 1.7 准备 commit

```
git status --porcelain
# 期望：仅在 revert 影响文件集合内
```

**Checkpoint 1**：用户 review 当前 diff 后才进入阶段 2。

## 阶段 2 — 调整 test_deployment_files.py

如果 §1.5 已经通过，本阶段主要是把残留 pack 引用收尾。

### 步骤 2.1 阅读测试文件

```
cat backend/skill-manager/tests/test_deployment_files.py
```

定位所有引用 `docker-compose.skill-packs.yml` 的断言。

### 步骤 2.2 删除或反向断言

将"该 compose 必须存在"的断言改为"该 compose 必须不存在"。

### 步骤 2.3 重跑测试

```
cd backend/skill-manager
./.venv/bin/python -m pytest tests/test_deployment_files.py -v
# 期望：调整后绿
```

**Checkpoint 2**：测试绿后进入阶段 3。

## 阶段 3 — 写 `clean_nas.py`

### 步骤 3.1 创建脚本骨架

```
mkdir -p backend/skill-manager/scripts
touch backend/skill-manager/scripts/__init__.py
```

### 步骤 3.2 实现 clean_nas.py

按 design §4 完整实现：
- argparse：`--paths`（默认 `./clean_nas.paths.json`）、`--dry-run | --apply`（互斥）。
- 阶段 0-3 函数化（纯函数 + I/O 分离，便于 dry-run / apply 共用）。
- 备份：BakManager 持有 ISO timestamp 一次性后缀。
- 错误：自定义 `CleanNasError`（继承 `RuntimeError`），所有阶段失败抛出。
- 退出码：成功 0；任何阶段失败 1；用户中断（KeyboardInterrupt）2。

### 步骤 3.3 准备 paths.example.json

```
{
  "state_db": "/home/<user>/skill-manager/state/skill-manager.sqlite3",
  "openclaw_root": "/home/<user>/.openclaw/workspace/skills",
  "hermes_root": "/home/<user>/.hermes/skills",
  "openclaw_config": "/home/<user>/.openclaw/openclaw.json",
  "github_cache_root": "/home/<user>/skill-manager/github-cache",
  "pack_discovery_state_dir": "/home/<user>/skill-manager/state"
}
```

将 `clean_nas.paths.json` 加入 `.gitignore`（仅本机使用，不进版本控制）。`.gitignore` 已存在则追加；不存在则新建。

### 步骤 3.4 自检

```
cd backend/skill-manager
python -m scripts.clean_nas --help
# 期望：列出 --paths / --dry-run / --apply 选项

# 在仓库目录内准备一个测试 paths.json（用 master 当前实际不存在的 fake 路径）
# 期望：阶段 0 I/O 失败打印明确错误、退出码 1
```

**Checkpoint 3**：`--help`、`--dry-run` 在不可达路径下报错语义清晰后进入阶段 4。

## 阶段 4 — NAS 现场清理文档

### 步骤 4.1 在 `docs/skill-manager-nas-setup.md` 反向之后的位置加一段

位置：`§ 回滚` 与 `§ 安全要点` 之间插入 `## 一次性撤销整包仓库软链（NAS 清理）`，内容：

```md
## 一次性撤销整包仓库软链（NAS 清理）

仅在 pack 体系被 revert 后用作一次性清理。脚本包含 dry-run 模式与备份机制。

1. 在管理台确认已 merge 含 `revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署` 的 commit 至 master，pull 至 NAS 仓库。
2. 在 NAS 主用户上：
   ```bash
   cp ~/personal-web/backend/skill-manager/scripts/clean_nas.paths.example.json \
      ~/clean_nas.paths.json
   $EDITOR ~/clean_nas.paths.json   # 填 6 个绝对路径
   ```
3. dry-run：
   ```bash
   cd ~/personal-web/backend/skill-manager
   python -m scripts.clean_nas --paths ~/clean_nas.paths.json --dry-run
   ```
   按打印计划与用户核对：将被 DROP 的表数、删除的软链数、移除的 extraDirs 项数、清理的缓存目录数。
4. apply：
   ```bash
   python -m scripts.clean_nas --paths ~/clean_nas.paths.json --apply
   ```
   每个破坏性操作写回 `.bak.<ISO ts>` 备份；SQLite 在 DROP 前拷贝为 `.sqlite3.bak.<ts>`。
5. 现场自检：
   ```bash
   sqlite3 ~/skill-manager/state/skill-manager.sqlite3 ".tables"
   # 不应出现 github_pack / legacy_github_pack_member / github_pack_history
   ls -la ~/.hermes/skills | grep '^l' | grep -E 'github-'
   # 零结果
   ls -la ~/.openclaw/workspace/skills | grep '^l' | grep -E 'github-'
   # 零结果
   ```
6. 在管理台对若干 skill 重新"发布计划 → 发布"，验证旧链路工作（每包独立软链、realpath 指向受控根）。

回滚：脚本不会自动回退现场；如 apply 后发现错误，从 `openclaw.json.bak.<ts>` 恢复 + git revert revert 已合 commit + 重新运行管理台。
```

### 步骤 4.2 自检

读 review 确保未引入 pack 段落与未删其它段落。

**Checkpoint 4**：文档审阅通过后进入阶段 5。

## 阶段 5 — 自检 + 提交

### 步骤 5.1 完整自检

```
git status
# 期望：仅在两个 revert 后修改文件 + clean_nas.py + 文档段
```

```
cd backend/skill-manager && ./.venv/bin/python -m pytest tests/ -v
cd apps/skill-manager && pnpm vitest run && pnpm tsc --noEmit && pnpm next build && NODE_ENV=production pnpm next build && pnpm lint
```

### 步骤 5.2 提交 revert

```
git commit -m "revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署

This reverts commit 3f9d6b5c601cfe8a89eb1b2e19a49bdbc90dedce.

依据 task 10-13-rollback-skill-manager-packs 的 prd.md §R1-R7、design.md §2 与
implement.md §阶段1。Pack 体系声称 hermes 也走整包发布但实现只适配 openclaw；
详见 https://<monorepo>/-/issues/<id> 关闭该争议。"
```

注意：commit 末尾的 attribution 必须按本会话得到的指示：
```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
```

### 步骤 5.3 提交 96a06ee 的 revert

```
git commit -m "revert: chore: 补交 skill-manager 测试、部署文件与 rss-relay uv.lock

This reverts commit 96a06ee1fd6581a513c3c61f0ad0841c08e43e75.

实现层仅回退 pack 测试与 docker-compose.skill-packs.yml；rss-relay uv.lock 由
单独保留性提交维护（见下一个 commit），与 pack 回滚解耦。"
```

### 步骤 5.4 提交 rss-relay uv.lock 保留性提交（如果 OI-4 决定拆分）

仅在 prd.md OI-4 决策为"拆分"时执行：

```
# 把 backend/rss-relay/uv.lock 从撤销集里 re-add
git checkout HEAD~2 -- backend/rss-relay/uv.lock
git add backend/rss-relay/uv.lock
git commit -m "chore: 保留 rss-relay uv.lock（与 pack 撤销解耦）

原 commit 96a06ee 一并 append 了 rss-relay uv.lock；pack 体系回滚仅撤销
pack 测试与 docker-compose.skill-packs.yml；保留 rss-relay 锁定以保持
monorepo 其它 uv 项目惯例。"
```

### 步骤 5.5 提交 NAS 清理脚本

```
git add backend/skill-manager/scripts/clean_nas.py backend/skill-manager/scripts/__init__.py
git add docs/skill-manager-nas-setup.md
git add backend/skill-manager/tests/test_deployment_files.py   # 阶段 2 调整（如有）
git commit -m "feat(skill-manager): 新增 pack 体系一次性清理脚本

伴随 revert 10-13-rollback-skill-manager-packs；仅供一次性现场使用，
不写入 CI / cron。详见 docs/skill-manager-nas-setup.md §一次性撤销整包仓库软链。"
```

### 步骤 5.6 推送与 PR

```
git push origin master
```

或者：
```
git push origin <branch>
gh pr create --base master --title "revert(skill-manager): 撤销整包仓库软链体系" --body-file <body.md>
```

`body.md` 内容含本 `prd.md` 摘要、`AC` 清单、与 `verification` 步骤。

### 步骤 5.7 提交后最终自检

```
git log --oneline -5
# 期望：两个 revert + 1 个保留性提交（可选）+ 1 个清理脚本提交

git log --oneline --grep "^revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署"
# 期望：1 个匹配

git log --oneline --grep "^revert: chore: 补交 skill-manager 测试、部署文件与 rss-relay uv.lock"
# 期望：1 个匹配
```

**Checkpoint 5**：四个 commit 全部 push 至 origin。

## 复盘与归档

合 PR 后：
- 在 `.trellis/tasks/10-13-skill-manager-repo-pack-symlinks/` 加一个 `OUTCOME.md`（仅记录"撤销理由 + revert commit hash 引用"），原 `prd.md` / `design.md` 等档案保留。
- 本任务的 `verification.md` 写入最终合 PR 的 id、commit hash、`test_deployment_files.py` 调整前后对比，并标 `status: completed`。

## 回滚点（紧急 stop）

阶段 0-3 之间任何一步如出现意外：
- 立即 `git revert --abort`（如还在 revert 中）。
- 回到 master 头部 commit，不带任何撤销改动。
- 让用户重新评估 next-step。

阶段 5 commit 已合后如要回退：
- 新建 revert-of-revert（即 `git revert <revert-commit>`），最少变动。
- NAS 状态由 `clean_nas.py .bak.<ts>` 恢复。

## 验收前 demo 流程

按 `prd.md` 的 `AC1-AC11` 全部走一遍。具体实例：

- AC1：grep `github_pack` 等关键字在 `apps/skill-manager/src`、`backend/skill-manager/src`、`backend/skill-manager/tests`、`nginx/web.conf`、`deploy/` 下零结果。
- AC2：pytest 与 vitest 通过。
- AC3-AC5：grep / `git log` 检查 db.py / main.py / models.py 干净。
- AC6：grep `github-packs` 在 nginx/web.conf 零结果；docker-compose.skill-packs.yml 不存在。
- AC7：grep "整包" 在两份文档除历史 changelog 之外零结果。
- AC8：pytest 全集通过。
- AC9：dry-run / apply demo（不需要真跑 apply，dry-run 演示足够）。
- AC10：本地 `pnpm dev` + 浏览器访问。
- AC11：clean_nas.py 仅依赖标准库。
