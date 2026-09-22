# skill-manager 接管并废弃源库 sync 工具链

## Goal

废弃 F:\personal-projects\skills 的手动 sync 工具链（`scripts/sync_*.py` 等），删除其数据文件与配套代码；skill-manager（SQLite 登记 + 对账）成为唯一登记真源。

已决策（用户确认）：**不扩展 claudecode/codex 目标**、github 按 **HEAD** 发布、4 个退役条目**保留 + source_missing 提示**、**不支持 skills_subdir**。

## Requirements

- R1 源库删除数据文件：`registry.json`、`registry.json.bak`、`sync-config.json`、`skill-agent-matrix.html`
- R2 源库删除脚本：`scripts/registry_loader.py`、`scripts/sync_skills.py`、`scripts/sync_github_skills.py`、`scripts/sync_github_versions.py`
- R3 源库删除测试：`tests/test_macro_skill_catalog.py`（断言 registry.json 内容，删除后必失败）
- R4 源库 `README.md` 更新：移除工具链维护/运行说明，标注登记与发布由 skill-manager 接管
- R5 本仓库删除：`backend/skill-manager/scripts/migrate_registry.py`（唯一消费者是 matrix.html → registry.json，两者均删）
- R6 数据确认：github 3 条（luopan / ui-ux-pro-max / uzi-skill）已在 SQLite，无丢失；local 2 条新条目（bond-market-macro-impact-skill / a-share-macro-impact-skill）真实环境首次 `GET /api/skills` 对账自动登记；4 个退役条目保留并显示 source_missing
- R7 保留不动：`~/.claude/skills/git-commit-push` 与 `~/.codex/skills/git-commit-push` junction（claudecode/codex 在用，工具链产物）；`.cache/` 机器本地缓存（github-versions.json / github-skills/）；`docs/superpowers/` 无关文档；`~/.claude/skills` 下 4 个过期 symlink（旧仓库残留，另案处理）

## 非目标

- 不扩展 skill-manager `TargetKey`（claudecode/codex 不纳入管理）
- 不补 github tag 固定逻辑（发布固定检出 HEAD）
- 不支持 per-target skills_subdir（统一发布到 `${target_root}/${skill_id}`）
- 不迁移、不删除现有 junction（git-commit-push 继续以工具链产物形式存在）

## Acceptance Criteria

- [ ] R1–R3、R5 文件全部删除；源库与 personal-web 两处 `git status` 干净（删除可追溯）
- [ ] 源库 grep 确认无 `sync_*.py` / `registry_loader.py` / `registry.json` / `sync-config.json` / `skill-agent-matrix` 引用残留（README 已更新内容除外）
- [ ] skill-manager 后端 `uv run pytest tests/ -v` 全绿
- [ ] 真实环境重启后 `GET /api/skills` 列表正常：github 3 条保留；local 对账出 2 条新条目、4 条退役条目显示 source_missing
- [ ] `~/.claude/skills/git-commit-push` 与 `~/.codex/skills/git-commit-push` junction 仍存在且可用
