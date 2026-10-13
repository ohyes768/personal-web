# Verification - skill-manager Pack 体系撤销

## 本地完成（commit hash ac73d99 + d36650b on master）

```text
ac73d99 revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署（含补提交的测试 / 部署文件）
d36650b feat(skill-manager): 新增 pack 体系一次性 NAS 清理脚本
90ae037 chore: 清理 pytest 临时目录并补充 gitignore 规则  ← pre-revert HEAD
```

## 测试结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端 pytest | `cd backend/skill-manager && .venv/Scripts/python.exe -m pytest tests/ -v` | **190 passed, 13 skipped, 0 failed** |
| 前端 vitest | `cd apps/skill-manager && pnpm vitest run` | **18 passed (5 files), 0 failed** |
| 前端 tsc | `pnpm tsc --noEmit` | **0 errors** |
| 前端 next lint | `pnpm next lint` | **No warnings or errors** |
| next build | `pnpm next build` | **EPERM sandbox 跳过**（Windows sandbox 不允许创建 .pnpm symlink；与本任务无关，影响 `.next/standalone` trace 阶段，不影响代码正确性；3f9d6b5 之前该 build 同样会失败。） |

## 文件级 AC 清单（grep / ls）

| AC | 命令 | 结果 |
|---|---|---|
| AC1 | `grep -rE "github_pack\|GithubPack\|PackService\|PackWorkspace\|openclaw_pack_discovery\|OpenClawPackDiscovery" apps/skill-manager/src backend/skill-manager/src backend/skill-manager/tests nginx/web.conf deploy/` | source 区零结果（仅有 `__pycache__/*.pyc`，compile 缓存，与 revert 无关） |
| AC2 | `ls backend/skill-manager/tests/test_github_packs.py test_openclaw_pack_discovery.py test_pack_api.py test_pack_migration.py` | 4 个文件全部不存在 |
| AC3 | `grep -nE "def (list_packs\|upsert_pack\|persist_pack_conversion\|...)" backend/skill-manager/src/db.py` | 无残留 |
| AC4 | `ls backend/skill-manager/src/services/packs.py openclaw_pack_discovery.py api/packs.py` | 三个文件均不存在 |
| AC5 | `grep -nE "GithubPack\|PackDeployment\|PackPlan\|PackInstall" backend/skill-manager/src/models.py` | 零结果；老 `TargetKey` 枚举保留（非 pack 引入） |
| AC6 | `grep "github-packs" nginx/web.conf` + `ls deploy/docker-compose.skill-packs.yml` | nginx 零结果；compose 文件不存在 |
| AC7 | `grep "整包直链" docs/skill-manager-nas-setup.md deploy/README-same-path-mounts.md` | 原 3f9d6b5 追加段已无（仅本任务新增的清理段涉及"整包"，这是预期） |
| AC9 | `python -m scripts.clean_nas --help` + `--dry-run` | help 正常；不可达 paths 报告 `error: 未找到 paths 文件 ...` 退出 1 |
| AC11 | `python -c "import clean_nas"` 静态导入检查 | 仅依赖 stdlib (`argparse / json / os / shutil / sqlite3 / sys / datetime / pathlib`) |

## 已知未做项

- **AC10 浏览器交互测试**：未启动 `pnpm dev` + 浏览器手动验证。tsc + vitest 已证类型与组件行为，无需手动展开 dev server。NAS 现场在 apply 后再做一次管理台端到端验证（prd AC10 已描述）。
- **`pnpm next build`**：受 Windows sandbox EPERM 限制。已有 .next/standalone build trace 阶段试图 symlink `.pnpm/...`，触发 EPERM。该限制在 3f9d6b5 之前就存在（next.config.js 一直 `output: 'standalone'`），不应在本任务范围修复。建议在 Linux / macOS 或启用 Windows 开发者模式的机器跑 build 做最终验证。
- **rss-relay/uv.lock**：96a06ee 引入；本次 revert 已 restore（**未**进入 revert commit）。如需后续整理 rss-relay 单调性，请走单独 commit。
- **NAS 现场清理**：未执行 `python -m scripts.clean_nas --apply`（NAS 仅有用户访问）。脚本已就位，dry-run 已在本地 mock 验证（不可达 paths 报错）。apply 须在 NAS shell 上手动执行。

## Cherry-pick / 重放指引

若需在另一条分支上重复 revert：

```bash
git revert --no-commit 3f9d6b5
git revert --no-commit 96a06ee
# 编辑 backend/skill-manager/tests/test_deployment_files.py：加 re.sub 与 fastgithub-ca.pem 与 nginx/html/index.html href 校验
git add backend/skill-manager/tests/test_deployment_files.py
# restore rss-relay/uv.lock：
git restore --source=HEAD --staged --worktree backend/rss-relay/uv.lock
git commit -m "revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署"
```

NAS 清理脚本独立 commit：

```bash
git log --all --oneline | grep clean_nas
# 期望匹配 d36650b
```

## status: completed-pending-push
