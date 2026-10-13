# 技术设计：Skill Manager Pack 体系撤销

## 1. 已确定的边界

- 撤销是"恢复"而不是"重写"。撤销后源码等价于 `3f9d6b5^` + `96a06ee^` 之上的独立提交（`307c7d0` 等 12 个 commit 原样叠加），不允许借机顺手修复无关 bug、不允许重命名、不允许新增或删除非 pack 相关的测试用例。
- 撤销产物 = 两个 `git revert` commit + 一个 NAS 清理脚本。脚本是新的，因为它不可从任何已存在 commit 派生；其余代码改动 100% 通过 `git revert` 完成。
- 不动 `nginx/web.conf` 中 `/skills` 与 `/api/skills` 路由块；仅撤回 `3f9d6b5` 追加的 `/api/github-packs` 路由。
- 不动 `.env` / `.env.local` / docker compose 顶层 override；只要 `deploy/docker-compose.skill-packs.yml` 被删除，引用消失即可。
- NAS 清理脚本必须保证 idempotent、出错即停、每个破坏性操作前可恢复。
- 不重写 `Publisher` / `git_cache.py` 的算法；保留 `3f9d6b5` 之前版本的语义。

## 2. 撤销策略：两个 revert commit

### 2.1 commit 序列

```
master (current)
  ├── revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署     ← 主要 revert
  └── revert: chore: 补交 skill-manager 测试、部署文件与 rss-relay uv.lock  ← 补刀
```

理由：
- `3f9d6b5` 与 `96a06ee` 是两次独立的开发动作；合并成一个 revert 会失去彼此隔离的回退空间（万一 pack 测试想分批回退、rss-relay uv.lock 不想动，可以分别走）。
- `revert` 的 commit message 由 git 自动产出 `revert: <原 commit subject>`，加上 `This reverts commit <hash>.` 与回滚理由段，正文引用 `prd.md` 与本 `design.md` 的关键段落，便于事后追溯。

### 2.2 是否走 `--no-commit` 手动解冲突

按 `git revert` 三阶段策略：

1. **第一次尝试**：`git revert --no-commit 3f9d6b5`，再 `git revert --no-commit 96a06ee`。两次合并一次提交，冲突集中处理。
2. **冲突来源预估**（基于 §1 已确认事实）：
   - `apps/skill-manager/src/app/page.tsx`：3f9d6b5 改前/改后差异包括 `RegisterGithubDialog` 替换为 `PackWorkspace`；后续 `f67f15f`、`31f2e5f`、`36c8f65` 修改的是 `RegisterGithubDialog.tsx` 与 `task_manager.ts`，未触及 `page.tsx` → 应无冲突。
   - `apps/skill-manager/src/components/TaskProgressDialog.{tsx,test.ts}`：`e674984`、`1c9400e`、`05a2c4c`、`2c3c173`、`376d12f` 修改了它们；`3f9d6b5` 在该文件加了 14 行（pack 路径上共享轮询逻辑）。重合并时 `1c9400e` 后端的 +14 vs 撤销时反向 −14 会冲突 → 解决预案见 §2.3。
   - `apps/skill-manager/src/components/ConfirmActionDialog.tsx`：`3f9d6b5` +8 行（适配 pack 流程）；非 pack commit 未动 → revert −8 后无冲突。
   - `apps/skill-manager/src/lib/types.ts` 与 `apps/skill-manager/src/lib/api.ts`：`3f9d6b5` +41 / +12；非 pack commit（`5fbbea6` +9、`7d77b94` +13）部分触碰过 `types.ts` → revert 时可能冲突 → 解决预案见 §2.3。
   - `apps/skill-manager/src/lib/useGithubTask.ts`：`3f9d6b5` +6（引入 pack 路径分支）；非 pack commit 未动 → revert −6 后无冲突。
   - `apps/skill-manager/next.config.js` 与 `nginx/web.conf`：非 pack commit 未动 → revert 无冲突。
   - `backend/skill-manager/src/api/routes.py`：`3f9d6b5` +43、`5fbbea6` +81、`307c7d0` +113、`36c8f65` +14；revert 3f9d6b5 的反向 −43 会与上述三者交汇在 routes.py — **可能冲突**。解决预案见 §2.3。
   - `backend/skill-manager/src/db.py`：`3f9d6b5` +55（pack 表 + 12 方法）、`5fbbea6` +78（export_target）、`307c7d0` +20；revert −55 后无冲突（只删新增，保留 `5fbbea6` / `307c7d0` 增量）。
   - `backend/skill-manager/src/models.py`：`3f9d6b5` +83（pack models）、`307c7d0` +21（export_target model）、`5fbbea6` +42（更多 export 字段）；revert −83 后可能与 `307c7d0` / `5fbbea6` 留下的 import 或类型在同区域 — **可能冲突**。解决预案见 §2.3。
   - `backend/skill-manager/src/services/task_manager.py`：`3f9d6b5` +32、`36c8f65` +38/-19；两区域不重叠，重合并无冲突（若重叠走 §2.3）。
   - `backend/skill-manager/src/services/git_cache.py`：`3f9d6b5` +5（pack 适配）、`36c8f65` +41（cache 版本化）；区域分离，无冲突。
   - `backend/skill-manager/src/services/migration.py`：`3f9d6b5` +4（pack 迁移钩）、`5fbbea6` +14（export_target 迁移）、`307c7d0` +4；revert 时 −4 会撞上 `5fbbea6` 的 import 块 — **可能冲突**。
   - `backend/skill-manager/src/main.py`：`3f9d6b5` +37（替换 lifespan 中 `migrate_legacy_cache` / `republish_active_github_skills` 为 `packs.migrate_legacy` / `packs.recover_conversions`，并 import `packs_router` + 注册全局 `PackError` 处理）。无其它 commit 动 main.py → revert 无冲突。
   - `backend/skill-manager/src/config.py`：`3f9d6b5` +2（`openclaw_config_path` 字段）。无其它 commit 动 config.py → revert 无冲突。
   - `backend/skill-manager/tests/test_deployment_files.py`：`3f9d6b5` +38、`5fbbea6` +9；revert 后 −38 与 `5fbbea6` +9 互相不重叠（区域分离），仅断言文本可能冲突 → §2.3。
   - `deploy/README-same-path-mounts.md` 与 `docs/skill-manager-nas-setup.md` 都只在末尾追加段落，revert 直接删段，无冲突。
   - `.trellis/spec/**/*.md` 与 `.trellis/spec/check.jsonl` / `implement.jsonl` / `design.md` / `implement.md` / `prd.md`：与代码无关，revert 时整段恢复（这些 spec 文件本来就是 3f9d6b5 引入/修改的）。

### 2.3 冲突解决预案

按 diff 区域逐个解：

**`api/routes.py`**：保留 `5fbbea6` 与 `307c7d0` 的 `/api/export-targets` 路由块；保留 `36c8f65` 的 cache 优先逻辑；撤回 `3f9d6b5` 引入的 `packs_router` mount 与 `/api/github-packs` 视图。解冲突时先看 hunk 属于哪一类：
- 加 import 的 hunk：移除 pack import。
- 视图块：保留 export-targets + cache 优先；删除 `/api/github-packs/...`。
- `app.include_router` 块：`main.py` 的 revert 自然处理，此处不出现。

**`models.py`**：保留 `5fbbea6` 的 `CreateExportTarget` / `UpdateExportTarget` 字段；保留 `307c7d0` 的导出目标 model；撤回 `3f9d6b5` 的 `GithubPack` / `PackDeployment` / `PackPlan*` / `PackInstall*` / `TargetKey` 等。冲突点是 import 行（`from ... import GithubPack` 等）— 删 import 即可。

**`migration.py`**：`3f9d6b5` 改动很小（仅 +4 用于 `republish_active_github_skills` 等新 import），与 `5fbbea6` 的 export_target 迁移不同区。revert 时仅清除与 pack 相关的 import，保留 `5fbbea6` 添加的 `migrate_export_targets`（如有）等。

**`TaskProgressDialog.tsx`**：`3f9d6b5` 在文件内引入 `useGithubTask` 的 pack 分支；非 pack commit 也修改此文件（如 `1c9400e` 加轮询）。revert 时删除 `3f9d6b5` 加的 pack 分支 if-else，保留 `1c9400e` 等的轮询结构。

**`types.ts`**：`3f9d6b5` +41 是 pack 类型 union 与枚举；非 pack commit（`5fbbea6` +9、`7d77b94` +13）是 export types。删 hunk 时按 union 内容判断是否提到 `Pack` / `pack` / `legacy` / `GithubPack` —— 是则删。

**`test_deployment_files.py`**：保留测试部署文件存在的断言；删除 pack 测试（`docker-compose.skill-packs.yml` 那一段）。如有硬编码 pack 路径或 pack compose 字段，做同样删除。

### 2.4 不在 revert 范围但属本次回滚对象的文件

- `deploy/docker-compose.skill-packs.yml`（96a06ee 创建，13 行）。
- `deploy/README-same-path-mounts.md`（`3f9d6b5` 在第 50 行后追加 9 行）。
- `docs/skill-manager-nas-setup.md`（`3f9d6b5` 在第 168 行后追加 25 行）。
- `nginx/web.conf`（`3f9d6b5` 在 L375 之后插入 15 行）。

这些 revert 1：1 反向还原；对 `.md` 文件的 revert 等价于删段；对 `.yml` 的 revert 等价于 `git rm`。

## 3. .trellis/spec/ 文档回滚

- `revert 3f9d6b5` 会反向应用 `prd.md` / `design.md` / `implement.md` / `implement.jsonl` / `check.jsonl` / `verification.md` / `research/findings.md` / `task.json` 的修改，达成"撤销对象的证据档案"还原为创建初版（其中 prd.md / design.md 等已于先前版本存在 —— revert 后会指向该任务当时的早期内容）。
- `.trellis/spec/guides/index.md`、`guides/skill-manager-export-targets.md`、`guides/skill-manager-frontend.md`、`guides/skill-manager-github-cache.md`、`guides/skill-manager-registry-sync.md` 中由 `3f9d6b5` 添加的段落同步反向。
- `.trellis/spec/backend/skill-manager/backend/index.md` 与 `backend/repo-packs.md` 不再需要存在 —— `revert` 反向化后 `repo-packs.md` 自动删除。
- 不为本次新增 spec 文档；撤销是 spec 中性事件。

## 4. NAS 清理脚本（`clean_nas.py`）

### 4.1 路径与依赖

位置：`backend/skill-manager/scripts/clean_nas.py`。

依赖：仅 Python 3.11+ 标准库（`argparse`、`json`、`pathlib`、`sqlite3`、`shutil`、`sys`、`datetime`、`os`）。不依赖第三方包。

入口：
```
python -m clean_nas [--paths <paths.json>] [--dry-run | --apply]
```
默认 `--dry-run`；必须显式 `--apply` 才落盘。

`paths.json` 样例：
```json
{
  "state_db": "/home/jackson.tang/skill-manager/state/skill-manager.sqlite3",
  "openclaw_root": "/home/jackson.tang/.openclaw/workspace/skills",
  "hermes_root": "/home/jackson.tang/.hermes/skills",
  "openclaw_config": "/home/jackson.tang/.openclaw/openclaw.json",
  "github_cache_root": "/home/jackson.tang/skill-manager/github-cache",
  "pack_discovery_state_dir": "/home/jackson.tang/skill-manager/state"
}
```

脚本启动时若 `paths.json` 不存在，提示用户复制 `clean_nas.paths.example.json`（同时新增到 `.gitignore` 之外管理，本任务无须提交加密信息）。

### 4.2 执行阶段（严格顺序，失败即停）

阶段 0：**只读盘点**
- 打开 SQLite。`SELECT COUNT(*) FROM github_pack / legacy_github_pack_member / github_pack_history` 各计数。
- 打开 `openclaw.json`：备份到 `openclaw.json.bak.<ts>`（前提：有写权限）。解析 `skills.load.extraDirs` 列表；与 `state_dir/openclaw-pack-discovery.json` 的 `added` 列表求交集 → 得到"本回滚需移除的 extraDirs 项集合"。
- 对 `openclaw_root` 与 `hermes_root` 各 `for entry in iterdir()` 识别 `github-` 前缀的软链 → 软链集合 S。
- 对 `github_cache_root/repos/` 下每个目录，扫 `{hermes_root, openclaw_root}` 中是否仍有软链 `realpath` 指向它 → 计算"无引用"缓存目录集合 N。

阶段 1：**打印计划（无论 --dry-run 与否都打印）**
```
[1] SQLite DROP TABLE:
    - github_pack            (<n> rows)
    - legacy_github_pack_member (<n> rows)
    - github_pack_history    (<n> rows)
[2] File removals:
    - state/openclaw-pack-discovery.json
    - state/openclaw-pack-discovery-pending.json
    - <m> package symlinks in <hermes_root>:
        github-xbtlin-ai-berkshire-<hash>  →  <cache>/xbtlin__ai-berkshire
    - <m> package symlinks in <openclaw_root>:
        ...
[3] File edits:
    - openclaw.json:
        remove extraDirs:
            + /home/jackson.tang/.openclaw/workspace/skills/github-xbtlin-ai-berkshire-<hash>/codex-skills
            ...
[4] Cache cleanups (only if no remaining inbound symlinks):
    - <github_cache_root>/repos/xbtlin__ai-berkshire
```
停在这里等待用户确认。

阶段 2：**应用**（仅 `--apply`）
- DROP 三表（按顺序：`github_pack_history` → `legacy_github_pack_member` → `github_pack`）。
- `os.remove` 三个 JSON 台账（含 `.pending`）。
- 遍历 S 列表，删除每条软链。删除前 `realpath` 必须仍在受控缓存根内，否则终止阶段、报告违规项。
- `pathlib.Path.read_text` → `json.loads` → `json.dumps(indent=2, ensure_ascii=False)` → `os.replace` 写回；写回前再次断言 `extraDirs` 列表已成功修改（diff 校验）。
- `force_remove_tree(path)` 清理 N（仅当 path 已无 inbound 引用）。

阶段 3：**审计打印**
- 重新打开 SQLite，确认三表不存在。
- 重新 `readlink` 受影响的安装根目录，确认已无 `github-` 前缀项。
- 重新 `loads(openclaw.json)`，确认 `extraDirs` 列表与 print 计划一致。
- exit 0。

### 4.3 失败语义

- 阶段 0 任一步骤 I/O 失败（文件不存在是 OK；权限 / 解析失败是 fatal）→ exit 1。
- 阶段 2 DROP TABLE 抛异常 → 不继续；后续步骤终止；已经做的 DROP 无法撤销但磁盘备份存在。
- 阶段 2 删除软链时 `realpath` 越过受控根 → 立即停手 + 报告；后续不再删。
- 阶段 2 openclaw.json 写回 diff 不一致 → 终止；从 `.bak.<ts>` 还原。
- 阶段 2 清理缓存时仍有 inbound 引用 → 该项跳过 + 报告。

### 4.4 备份策略

- 每个 `.bak.<ts>` 用 ISO timestamp 后缀；原地不循环（不复用名称）。
- 不引入复杂 backup-set 概念；用户自行 `~/.local/share/...` 集中管理。
- `state/skill-manager.sqlite3.bak.<ts>` 在 DROP 前做 `shutil.copy2` 全文件拷贝。

### 4.5 不动的事

- `~/.gitignore`、`.env*`、`docker-compose.nas.yml`、nginx 配置文件 — 全不动。
- `skill-manager-state` docker volume 内除上面 SQLite 表外的其它内容（export_target 等）保留。
- 用户在 `openclaw.json` 中手写的 `extraDirs` 项（与台账 `added` 列表求交集才删）。

## 5. 数据库 schema 改动细节

`db.py` schema 字符串 `_SCHEMA`：
- 保留现有部分（`state_migration`、`export_target`、`deployment`、`deployment_history`、`github_check`、`registry_skill`、`_COLUMN_MIGRATIONS`）。
- 删除 `3f9d6b5` 追加在 `_SCHEMA = """` 内的三张 pack 表创建语句（如存在）。
- `_SCHEMA` 之外、`__init__` 内 `with closing(...) as conn, conn: conn.executescript("""CREATE TABLE IF NOT EXISTS github_pack...""")` 这块 `inline SQL` 也在 revert 后消失。

`_COLUMN_MIGRATIONS`：维持现状，不为回滚添加/删除项。

不写"曾有 pack"的负向兼容标记（如 `state_migration` 加一行 `packs_v1_dropped`） —— 因为回滚后这些表物理不存在，下次启动的 idempotent 创建依然不会创建它们。

## 6. 风险与回滚点

| 风险 | 表现 | 兜底 |
|------|------|------|
| `git revert` 冲突多于 §2.3 预案 | 反复手动解 | 接受更多手工合 — 不可接受的冲突面 = 试图"修复"无关代码；一旦发现，停下来与用户同步 |
| 旧 `migrate_legacy_cache` / `republish_active_github_skills` 内部隐式依赖 pack 表 | 启动 crash | revert 主体后跑 `pytest tests/` + `uvicorn` smoke；如失败查 traceback 找根因 |
| NAS `openclaw.json` 已被手工编辑 | `extraDirs` 中增删项不在台账 `added` 集合内 | 阶段 2 写回前 diff 校验；不一致即 terminate |
| 用户删库未走 `--apply` | 实质未改动，仅打印计划 | --dry-run 是默认；文档与脚本 argparse 双重提示 |
| 旧前端交互恢复后某一处仍引用 pack 类型 | TypeScript 编译错 | `pnpm tsc --noEmit` + `pnpm build` 是 PR 门禁 |
| 测试 `test_deployment_files.py` 残留对 pack compose 字段断言 | pytest fail | §2.3 已列出调整预案；如发现遗漏，做最小删除 |

## 7. 验证策略

PR 门禁：
- `backend/skill-manager/.venv/bin/python -m pytest tests/ -v` 绿。
- `apps/skill-manager`：`pnpm vitest run` 绿 + `pnpm next build`（dev 与 prod 两个 NODE_ENV）绿 + `pnpm tsc --noEmit` 绿 + `pnpm lint` 绿（保留项目既有 lint 配置）。
- `nginx/web.conf` 通过 `nginx -t`（调用 `./scripts/deploy-nas.sh nginx --dry-run` 或 `docker run --rm -v ${PWD}/nginx/web.conf:/etc/nginx/conf.d/web.conf:ro nginx nginx -t`）。

NAS 现场（不进 PR）：
- 跑 `python -m clean_nas --dry-run`，用户目视核对计划。
- 跑 `python -m clean_nas --apply`，按 §4.2 阶段 0-3 执行。
- 现场验证：
  - `openclaw.json` 内 `extraDirs` 列表符合预期；
  - 两个 skill 根下 `ls -l | grep -E 'github-'` 零结果；
  - `sqlite3 skill-manager.sqlite3 ".tables"` 不含 `github_pack*` / `legacy_github_pack_member`。
  - 在管理台上对若干 skill 重新"发布计划 → 发布"测试，确保旧发布链路真实工作。

## 8. 不在范围

- 不修改 `apps/housing-map`、`apps/dividend`、`apps/douyin` 等其他 app。
- 不调整 monorepo 的 `package.json` / `pnpm-workspace.yaml` / `uv.lock`（rss-relay 单独提交拆分见 prd OI-4）。
- 不重写 `clean_nas.py` 的 non-pack 清理能力（部署说明里"清理旧断链"的 `find` 命令保留在文档中）。
- 不为本次回滚做 changelog / release notes（仍在内网工具级别）。
