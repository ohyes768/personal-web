# 技术设计：废弃源库 sync 工具链

## 1. 边界

- 源库 `F:\personal-projects\skills` 是**独立 git 仓库**，当前 `git status` 干净（2026-09-22 确认）——所有删除均可经 `git restore` 恢复，无未提交工作丢失风险。
- personal-web 本仓库只删 `backend/skill-manager/scripts/migrate_registry.py`；skill-manager 运行时代码**零改动**（对账、source_missing、按 HEAD 发布均已在 task `09-22-skill-local-sync` 实现）。
- 机器本地 junction（`~/.claude/skills/git-commit-push`、`~/.codex/skills/git-commit-push`）不动；`.cache/` 本地缓存不动。

## 2. 清理清单

| # | 路径 | 归属 | 说明 |
|---|------|------|------|
| 1 | `skills/registry.json` | 源库 | 工具链登记真源，已无 skill-manager 读者 |
| 2 | `skills/registry.json.bak` | 源库 | 无任何消费者 |
| 3 | `skills/sync-config.json` | 源库 | agent 路径/enabled 开关，随工具链废弃 |
| 4 | `skills/skill-agent-matrix.html` | 源库 | legacy 唯一数据源，仅 migrate_registry.py 消费 |
| 5 | `skills/scripts/registry_loader.py` | 源库 | 共享加载器 |
| 6 | `skills/scripts/sync_skills.py` | 源库 | local → agent junction |
| 7 | `skills/scripts/sync_github_skills.py` | 源库 | github → 缓存 → junction |
| 8 | `skills/scripts/sync_github_versions.py` | 源库 | github 版本快照 |
| 9 | `skills/tests/test_macro_skill_catalog.py` | 源库 | 断言 registry.json，必失败 |
| 10 | `personal-web/backend/skill-manager/scripts/migrate_registry.py` | 本仓库 | matrix.html → registry.json 一次性迁移，输入输出均已删 |
| 11 | `skills/README.md` | 源库 | 更新：移除工具链说明，标注由 skill-manager 接管 |

## 3. 数据一致性（删除前无需导出）

- **github 3 条**（luopan / ui-ux-pro-max / uzi-skill）：SQLite `.skill-manager-dev/state/skill-manager.sqlite3` 已登记，无丢失。
- **local 条目**：真实环境首次 `GET /api/skills` 触发 `sync_local()`：
  - 源目录存在的（含 bond-market-macro-impact-skill、a-share-macro-impact-skill）自动登记；
  - 4 个退役条目（macro-overview / bond-market-overview / risk-appetite / exchange-rate）源目录已删，保留 + `source_missing=True`（既有行为）。
- registry.json 删除不产生数据丢失——它已无任何读者（skill-manager R6 已去除导入，工具链被本任务删除）。

## 4. 删除顺序与风险

- **顺序**：先删源库脚本（R2）与测试（R3）→ 再删数据文件（R1）→ 更新 README（R4）→ 删本仓库 migrate_registry.py（R5）。此顺序下任何一步中断，registry.json 仍可作工具链回退源。
- **误删恢复**：两仓库均有 git，`git restore <path>` 即可。
- **残留校验**：删除后全量 grep 兜底（R2 验收），确认无脚本引用残留。
- **junction 影响**：不触碰 git-commit-push junction，claudecode/codex 现有 skill 不受影响。

## 5. 不做的事（用户已决策）

- 不扩展 `TargetKey`（claudecode/codex 不纳入 skill-manager）。
- 不补 tag 选择逻辑（github 发布按 HEAD，工具链 tag 快照语义一并废弃）。
- 不支持 skills_subdir（hermes 关闭中，统一根目录发布）。
- 不清理 `~/.claude/skills` 下 4 个过期 symlink（旧仓库 `macro-fin-skill` 残留，另案）。
