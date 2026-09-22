# 执行计划：废弃源库 sync 工具链

前置：prd.md / design.md 已评审，用户已确认四项范围决策（不扩 target / 按 HEAD / 退役保留 / 无子目录）。
两处 git 仓库：源库 `F:\personal-projects\skills`（干净）、本仓库 `F:\personal-projects\personal-web`。

## 步骤

### 1. 源库删除脚本与测试（R2/R3）
- [x] `cd F:/personal-projects/skills && git rm scripts/registry_loader.py scripts/sync_skills.py scripts/sync_github_skills.py scripts/sync_github_versions.py tests/test_macro_skill_catalog.py`
- 验证：`git status --short` 显示删除暂存

### 2. 源库删除数据文件（R1）
- [x] `git rm registry.json registry.json.bak sync-config.json skill-agent-matrix.html`（.bak 未跟踪，用 `rm -f`）
- 验证：`ls` 确认文件消失

### 3. 源库更新 README（R4）
- [x] 重写 README：移除工具链说明，标注登记与发布由 skill-manager 接管
- 验证：grep README 无 sync 脚本命令

### 4. 本仓库删 migrate_registry.py（R5）
- [x] `git rm backend/skill-manager/scripts/migrate_registry.py`
- 验证：grep 本仓库无 `migrate_registry` 引用

### 5. 残留校验 + skill-manager 测试
- [x] 源库 grep 仅 `docs/superpowers/plans/*.md` 历史计划提及 skill-agent-matrix（非依赖，保留）
- [x] 本仓库：`uv run pytest tests/ -v` → 111 passed, 14 skipped

### 6. 真实环境验证（review gate）
- [x] 重启 8097 后端加载新代码；`GET /api/skills` 返回 22 条：3 个 github 保留；对账新增 a-share/bond-market 宏观、hk-ipo-backtest、hk-ipo-research、think-skill；4 个退役条目 `source_missing=True`
- [x] `~/.claude/skills/git-commit-push`、`~/.codex/skills/git-commit-push` junction 仍在（claudecode/codex 不受影响）

## 回滚点

- 所有删除均经 git，`git restore` 可整体回退；步骤 1–4 每步独立可逆。
- 步骤 5 残留校验失败 → 停止，恢复被引用文件再继续。

## 完成定义

- [x] PRD 验收标准全部达成；两处 git status 干净（仅删除/README 记录，未提交）；skill-manager 测试全绿；真实环境对账正确；junction 未受影响。
- [ ] 待用户决定：两仓库 commit、前端 UI 浏览器验证（可选）
