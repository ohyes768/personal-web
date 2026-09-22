# Research: skills 源库 sync 工具链全貌

- **Query**: 摸清 F:\personal-projects\skills 的 sync 工具链（registry_loader.py / sync_skills.py / sync_github_skills.py / sync_github_versions.py / sync-config.json / skill-agent-matrix.html / registry.json / README / docs / tests）
- **Scope**: internal（外部独立仓库，只读）
- **Date**: 2026-09-22

## 总览

F:\personal-projects\skills 是独立 git 仓库（非 personal-web 的一部分）。注册表（skill 清单 + agent 分配）以 `registry.json` 为唯一真源（可版本控制）；GitHub 版本快照（`latest_version`/`head_commit`/`checked_at`）是运行状态，存在机器本地 `.cache/github-versions.json`（不入 git）。发布方式是 Windows **junction**（`mklink /J`）。

**执行方式**：全部为**手动 CLI**。README 只提供命令行说明，仓库内无任何 cron / 计划任务 / .bat 引用（grep cron/schtasks/bat/ps1 仅命中 skill 内容如 hk-ipo 的 cron 场景，与工具链无关）。`logs/service.log` 为空。`.cache`、junction、registry.json.bak 均为机器本地状态。

---

## 1. scripts/ 四个脚本职责

### 1.1 registry_loader.py（共享加载器，无 CLI）
- 职责：三个 sync 脚本共用的注册表/版本快照读写。
- 输入：`registry.json`（真源，缺失即 `FileNotFoundError` 并提示先用 `migrate_registry.py` 生成）；`.cache/github-versions.json`（缺失返回空结构 `{"version":1,"updated":"","skills":{}}`）。
- 输出：`save_versions()` 原子写 `.cache/github-versions.json`（先写 `.json.tmp` 再 `replace`）。
- 明确契约：版本快照不写回注册表。

### 1.2 sync_skills.py（同步自研 local skill → 各 agent，junction）
- 输入：`sync-config.json`（agent 路径 + enabled）、`registry.json`（skills + agents 分配）。
- 逻辑：遍历 `config.agents`，`enabled` 为 false 跳过；取 `registry.agents[agent].skills`，只处理 `source=local` 且映射到 `<skills仓库>/<path>` 的条目；在 `<agent skills_dir>/<skill名>` 建 junction。
- 输出：junction（`cmd /c mklink /J`）。已是正确 junction 跳过（`[=]`）；旧链接先移除（junction/symlink 直接 `rmdir`，普通目录备份为 `.bak` 再删）。
- 选项：`--dry-run`、`--skill`、`--agent`、`--status`。
- 失败处理：逐行 try/except，单项失败打印 `[x]`，全部失败数非 0 时退出码 1；源目录缺失抛 `FileNotFoundError`。

### 1.3 sync_github_versions.py（刷新 GitHub 版本快照）
- 输入：`registry.json` 中 `source=github` 条目；`.cache/github-versions.json`。
- 逻辑：对每个 github skill 执行 `git ls-remote`（HEAD + `--tags --refs`，不走 GitHub REST API、无需 token）；`parse_tag` 解析语义化 tag，取**最新 semver tag**；无 tag 记 `HEAD@<短commit>`。
- 输出：`.cache/github-versions.json`（每个 skill 写 `latest_version`/`head_commit`/`checked_at`，顶层 `updated`；失败只记 `checked_at` 继续）。
- 选项：`--dry-run` 只看不写。
- 当前快照值（2026-09-20）：ui-ux-pro-max=v2.15.0、uzi-skill=v3.9.1、luopan=HEAD@499eb43。

### 1.4 sync_github_skills.py（clone/pull GitHub skill → 缓存 → junction）
- 输入：`sync-config.json`、`registry.json`、`.cache/github-versions.json`（`target_ref()` 从快照取 latest_version 或 head_commit）。
- 缓存：`.cache/github-skills/<skill id>/`（git clone/fetch），内容目录 = 缓存 + 注册表 `path` 字段（可为 `.`）；校验内容目录含 `SKILL.md`（缺失仅告警）。
- 输出：`<agent skills_dir>/<skill名>` junction → 缓存内容目录。
- 版本处理：ref 是 tag 名 → `--depth 1 --branch` clone；是 commit → clone 后 `checkout`+`reset --hard`。
- 选项：`--dry-run`、`--skill`、`--agent`、`--status`。
- 失败处理：缓存失败即 `return 1`（不继续建链接）；逐项 try/except。
- 当前缓存目录 `.cache/github-skills/` 只有遗留的 `UZI-Skill-test`（测试 clone），**真实缓存从未成功落盘或已被清理**——即该脚本在当前机器上未完整跑通过。

---

## 2. sync-config.json 结构

- `version: 1`、`link_type: "junction"`（声明性，脚本实际恒用 mklink /J）。
- `agents.<key>`：`enabled`（bool，脚本唯一开关）、`description`、`skills_dir`（agent skills 根）、可选 `skills_subdir`（hermes 用 `software-development`）、可选 `source_repo`（hermes）。
- 读取者：**仅 sync_skills.py 和 sync_github_skills.py**（registry_loader.py 与 sync_github_versions.py 不读）。
- 当前状态：claudecode=enabled、codex=enabled、openclaw=disabled、hermes=disabled。
  - 注意：registry.json 的 agents 分配是 openclaw→uzi-skill、hermes→uzi-skill、claudecode→git-commit-push、codex→[]；**当前实际被工具链管理的只有 claudecode 的 git-commit-push**（codex 空列表、openclaw/hermes 关闭）。

---

## 3. skill-agent-matrix.html（legacy）

- 是**旧版唯一数据源**：HTML 内嵌 `<script type="application/json" id="registry-data">` 数据块（themes / skills：name、source、dir 或 repo、theme、status、summary、github 版 latest_version/head_commit/checked_at；agents：description、skills_dir、skills_subdir、skills 列表）。
- 页内有 JS（勾选分配 + IndexedDB 文件句柄自动保存），即**人工编辑保存**维护，无程序化生成者。
- README 已标注 "(legacy) 旧版内嵌注册表，仅作历史参考，不再维护"；其内嵌 description 自称 "唯一数据源"（陈旧说法）。
- 读者：**只有 `backend/skill-manager/scripts/migrate_registry.py`**（在 personal-web 仓库内）从它提取 registry-data 生成 `registry.json`。除此之外无其他消费者。
- 已确认无其他文件引用它（grep 仅命中 README 与自身）。

---

## 4. registry.json 当前条目（version 3.0, updated 2026-09-20）

- **共 15 个 skill：local 12、github 3**。
- local 12（source=local，path 为源库内目录）：
  1. bond-market-macro-impact-skill（finance-macro）
  2. a-share-macro-impact-skill（finance-macro）
  3. monetary-policy-skill（finance-macro）
  4. money-supply-skill（finance-macro）
  5. entity-economy-skill（finance-macro）
  6. inflation-skill（finance-macro）
  7. git-commit-push（dev-workflow）
  8. think（agent-methods/think-skill）
  9. ask-me（agent-methods）
  10. skill-creator（agent-methods）
  11. find-skills（agent-methods）
  12. notes-deal（knowledge）
- github 3（path 均为 "."）：
  1. ui-ux-pro-max → https://github.com/nextlevelbuilder/ui-ux-pro-max-skill（design）
  2. uzi-skill → https://github.com/wbh604/UZI-Skill（investment-analysis，name=UZI-Skill）
  3. luopan → https://github.com/zhangxiaoqiang1991/luopan（investment-analysis）
- agents 分配：openclaw→[uzi-skill]、hermes→[uzi-skill]、claudecode→[git-commit-push]、codex→[]。
- 读者：registry_loader.py（经 3 个 sync 脚本）+ tests/test_macro_skill_catalog.py。skill-manager **已不再读**（R6 已移除 import_registry_json_if_empty）。README「外部 skill」表标注的"安装到"与 agents 分配不完全一致（如 ui-ux-pro-max 表里写 hermes，但 agents 里未分配）——纯文档口径差异。

---

## 5. README.md 与 docs/ 部署/运行说明

- README 是**唯一**运维文档：全部手动命令（见第 1 节各脚本"用法"），无 cron、无 NAS 部署说明、无定时器。
- 维护指南：新增 local / github skill、新增 agent 均为"改 registry.json + sync-config.json + 跑脚本 + 更新 README"。
- `docs/` 只有 `superpowers/plans/2026-09-21-macro-skill-sunsetting.md` 与 `superpowers/specs/2026-09-21-macro-skill-sunsetting-design.md`——关于宏观 skill 下线的实施计划（已随 171d40b 提交完成），**与 sync 工具链本身无关**，不构成删除依赖。

---

## 6. tests/ 目录

- 仅 `tests/test_macro_skill_catalog.py`（unittest）。
- 断言 registry.json 中 finance-macro 类 skill 恰好等于 6 个保留集（bond-market-macro-impact-skill / a-share-macro-impact-skill / monetary-policy-skill / money-supply-skill / entity-economy-skill / inflation-skill），且 4 个退役目录（macro-overview-skill / bond-market-overview-skill / risk-appetite-skill / exchange-rate-skill）的源目录不存在。
- **不测试任何 sync 脚本行为**——只校验注册表内容与退役目录状态。删除 registry.json 或脚本后此测试将报错。

---

## 7. 当前机器实况（2026-09-22 观察）

- `~/.claude/skills/git-commit-push` → junction 指向 `/f/personal-projects/skills/dev-workflow/git-commit-push`（Aug 12，工具链产物）。
- `~/.codex/skills/git-commit-push` → junction 指向同一源目录（Aug 12，工具链产物）。
- `~/.claude/skills/` 另有 4 个**过期** symlink 指向 `/f/personal-projects/macro-fin-skill/skills/...`（a-share-macro-skill / bond-market-overview-skill / entity-economy-skill / exchange-rate-skill，May 22 旧仓库时代，非当前工具链管理）。
- `~/.openclaw/workspace/skills`、`~/.hermes/skills` **均为空**（sync-config 中 openclaw/hermes 关闭）。
- `.cache/github-versions.json` 存在；`.cache/github-skills/` 只有测试残留。
- skill-manager 开发态：`.skill-manager-dev/state/skill-manager.sqlite3` 已有 3 个 github 条目（luopan、ui-ux-pro-max、uzi-skill）+ 13 个 local 条目（含 4 个已退役的 bond-market-overview-skill / exchange-rate-skill / macro-overview-skill / risk-appetite-skill，因 sync_local "已登记一律不动" 保留）；`deployment` 表为空（尚未发布过）；github_check 仅 uzi-skill 有记录。

## Caveats / Not Found

- 未发现任何 cron/调度证据，结论为"手动运行"（基于 grep 无命中 + README 只有命令）。
- sync_github_skills.py 是否在生产机器真实跑过存疑（缓存目录只有测试残留）。
- skill-agent-matrix.html 的生成者无法从代码确认（页内 IndexedDB 自动保存暗示人工编辑）。
