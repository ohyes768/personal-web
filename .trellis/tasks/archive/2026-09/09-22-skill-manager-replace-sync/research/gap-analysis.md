# Research: sync 工具链 vs skill-manager 差距分析

- **Query**: skill-manager 若要完全接管并废弃源库 sync 工具链，缺什么能力、删什么之前必须迁移/确认什么
- **Scope**: internal（对比 personal-web 仓库内 backend/skill-manager 与外部 skills 仓库工具链）
- **Date**: 2026-09-22

> 判定依据：backend/skill-manager 的 `src/api/routes.py`、`src/services/registry.py`、`src/services/publisher.py`、`src/services/git_cache.py`、`src/config.py`、`src/models.py`（TargetKey）、`scripts/migrate_registry.py`，以及 skills 仓库 `scripts/sync_*.py` / `sync-config.json`。

---

## 1. 职责覆盖矩阵

| # | sync 工具链职责 | 实现脚本/文件 | skill-manager 覆盖 | 说明 |
|---|---|---|---|---|
| 1 | 注册表维护（skill 清单 + agent 分配，版本可控） | registry.json | **部分覆盖** | SQLite `registry_skill` + API CRUD 是更强真源；但按设计**不读 registry.json**，github 条目须经 API 扫描登记，local 条目由 `sync_local()` 自动对账 |
| 2 | 本地 skill 自动发现 + frontmatter 元数据 | 手工登记 registry.json | **已覆盖** | `discover_local()` 扫源库含 SKILL.md 目录，`sync_local()` 惰性对账（GET /skills 触发）；frontmatter name/description 解析 |
| 3 | 自研 skill 发布到 agent | sync_skills.py（junction） | **已覆盖（机制不同）** | Publisher 原子 symlink 发布 + 计划预览；openclaw/hermes 两 target |
| 4 | GitHub skill 缓存 clone/pull | sync_github_skills.py | **已覆盖** | GitCacheService clone/fetch/checkout 到 `github_skill_cache_root/<id>`，SKILL.md 校验，scan 支持登记前扫描 |
| 5 | GitHub 远端版本检查/快照 | sync_github_versions.py | **部分覆盖** | `check_update()` ls-remote HEAD+tags 存 `github_check`；但工具链选**最新语义化 tag**（或 HEAD@commit）快照，skill-manager 只记 HEAD sha，tag 列表仅展示不选用 |
| 6 | 按版本 checkout 后发布 github skill | sync_github_skills.py | **部分覆盖** | `ensure_cached(skill, revision)` 检出指定 revision；发布 revision 取最近一次成功 check 的远端 HEAD，**非 tag 语义** |
| 7 | 多 agent 批量同步 | 脚本循环 config.agents | **已覆盖** | publish items 可多 target 批量；仅 openclaw/hermes |
| 8 | agent enabled 开关 | sync-config.json | **未覆盖** | 无 per-target enabled 概念；发布是显式逐 target，无"总开关/开关状态" |
| 9 | agent `skills_subdir`（hermes → software-development） | sync-config.json | **未覆盖** | 目标固定 `${target_root}/${skill_id}`，无子目录 |
| 10 | **claudecode / codex 两个 agent 目标** | sync-config.json | **未覆盖** | `TargetKey` 仅 `{openclaw, hermes}` |
| 11 | 同步状态查看（--status：链接/缺失/缓存） | 两个脚本 --status | **部分覆盖** | SkillCard.deployments + link_missing + cache_missing + source_missing；但仅 openclaw/hermes |
| 12 | 回滚 | 无 | **超额** | rollback_snapshot 快照 + 回滚端点 |
| 13 | 下架（移除链接） | remove_link（junction rmdir） | **已覆盖（有兼容坑）** | `unpublish` 仅删 symlink；**对 junction 会判为"普通目录/文件"而拒绝**（Python is_symlink 对 junction 返回 False） |
| 14 | 发布历史 / 部署状态持久化 | 无 | **超额** | deployment / deployment_history / github_check 表 |
| 15 | dry-run 计划预览 | --dry-run | **已覆盖** | `POST /skills/publish/plan` 只读预览（add/update/unchanged/blocked） |

### 已覆盖项小结
local 发布、github 缓存、版本检查、批量发布、预览、下架、回滚、状态持久化——skill-manager 均已具备或超出工具链。

### 未覆盖 / 部分覆盖 = skill-manager 接管需补的能力
1. **claudecode、codex 发布目标**（最关键的缺口）。当前机器上工具链唯一活跃管理的正是 `~/.claude/skills/git-commit-push` 与 `~/.codex/skills/git-commit-push` 两个 junction——这两个 skill-manager 完全无法管。
2. **agent enabled 开关**：无 per-target 开关；接管"关闭某 agent 发布"语义只能靠不发布实现，无持久化状态。
3. **per-agent `skills_subdir`**：hermes 的 `software-development` 子目录结构无法表达。
4. **按语义化 tag 固定版本**：工具链把最新 tag（或 HEAD@commit）作为版本真源并 checkout；skill-manager 发布固定 HEAD。若要保持"发布到最新 tag"而非"HEAD"，需要补版本选择逻辑（remote_tags 已取到，仅未选用）。
5. **junction 兼容**：Publisher 对现存 junction 目标视为普通目录拒绝覆盖/下架；接管真实 openclaw/hermes 目录前若残留工具链 junction 需先移除。

---

## 2. 废弃工具链的迁移依赖清单（删除前必须处理/确认）

按"缺谁谁先确认"排序，标注依赖文件 → 处置要求：

| 依赖文件/状态 | 删除前必须确认/迁移 | 处置 |
|---|---|---|
| **3 个 github skill**（ui-ux-pro-max / uzi-skill / luopan） | skill-manager SQLite 已登记全部 3 个（.skill-manager-dev/state/skill-manager.sqlite3），登记数据无丢失；但发布历史/版本语义要确认 | 确认 SQLite 登记无误后 registry.json 的 github 条目可弃 |
| **12 个 local skill** | SQLite 已有 10 个；缺 `bond-market-macro-impact-skill`、`a-share-macro-impact-skill`（源目录在，首次 GET /skills 对账自动补）；SQLite 中 4 个已退役条目（macro-overview-skill / bond-market-overview-skill / risk-appetite-skill / exchange-rate-skill）源目录已删，会显示 source_missing | 决定 4 个退役条目保留（source_missing 提示）还是清理；新 2 个无需手工 |
| **claudecode / codex junction**（~/.claude/skills/git-commit-push、~/.codex/skills/git-commit-push → skills 源库） | skill-manager 无这两个 target。删 junction 会**断开 claudecode/codex 正在用的 git-commit-push** | 三选一：skill-manager 增加 claudecode/codex target；或确认这两个 agent 不再需要该 skill 后删 junction；或手工维护 |
| **hermes `skills_subdir: software-development`** | skill-manager 目标结构 `${root}/${skill_id}` 不含子目录；生产 hermes skills 根路径语义需对齐 | 确认 hermes 生产路径用根目录还是软件工程子目录；必要时扩展 target 结构 |
| **`.cache/github-versions.json`** | 记录 tag 固定（v2.15.0/v3.9.1/HEAD@499eb43）；skill-manager 无 tag 固定语义 | 确认接受改按 HEAD 发布，或补 tag 选择逻辑后再弃 |
| **`skill-agent-matrix.html`** | 唯一消费者是 `backend/skill-manager/scripts/migrate_registry.py`（生成 registry.json）；registry.json 已就绪 | 确认不再需要重跑迁移后，可连同 migrate_registry.py 一起删 |
| **`registry.json.bak`** | matrix_server 自动回写备份，无任何消费者 | 可直接删 |
| **`tests/test_macro_skill_catalog.py`** | 断言 registry.json 内容；删 registry.json 后必失败 | 随工具链一并删除 |
| **`docs/superpowers/*`** | 宏观 skill 下线计划文档，与工具链无关 | 不构成删除依赖，可保留或另行归档 |
| **过期 symlink 残留**（~/.claude/skills 下 4 个指向 /f/personal-projects/macro-fin-skill 的链接） | 与工具链无关，但同目录清理时易误伤 | 接管清理时知晓即可，不阻塞 |

### 特别提示（迁移期最易踩的坑）
- **junction 与 symlink 不互认**：工具链用 `mklink /J` 建 junction；skill-manager Publisher 用 `path.is_symlink()` 判定受管链接（junction 返回 False → 视作普通目录 → 拒绝覆盖/下架）。若 openclaw/hermes 目标位置存在工具链旧 junction，skill-manager 发布会 blocked。
- **github 版本语义差异**：工具链发布"最新 tag"，skill-manager 发布"最新 HEAD"。uzi-skill 当前远端 tag 到 v3.9.1、skill-manager check 的 HEAD=650788c——两者不一定同版本。
- **registry.json 与 SQLite 已双向漂移**：SQLite 多 4 个退役 local 条目、少 2 个新 local 条目；github 条目两边一致（3 个）。废弃工具链后 registry.json 不再是真源，漂移问题随其删除而终结，但 4 个退役条目需先决策。

---

## 3. 结论

skill-manager 已能覆盖工具链绝大部分职责（local 发布、github 缓存与检查、批量发布、预览、下架、回滚、持久化）。**接管前必须先补齐/确认三件事**：
1. claudecode / codex 两个 agent 目标（当前唯一活跃被管对象无法迁移）；
2. per-agent enabled 开关与 skills_subdir（hermes 结构）；
3. github 版本固定语义（tag vs HEAD）以及 junction→symlink 的目标兼容性。
以上确认完毕后，registry.json / sync-config.json / skill-agent-matrix.html / registry.json.bak / scripts/sync_*.py / tests/ 均可整体废弃，skill-manager 的 SQLite 与源库目录对账成为唯一真源。
