# Skill Manager 自研 Skill 登记与对账（sync_local）

> **Purpose**: 讲清自研（`source: local`）Skill 如何进入登记真源、`source_missing`
> 语义，以及 2026-09-22 源库 sync 工具链废弃后的遗留状态。改 skill-manager
> 登记/列表流程前必读。

---

## 登记真源与数据流

**SQLite `registry_skill` 表是唯一登记真源**，环境本地。自研 Skill 不靠手工
登记、也不靠源库 registry.json——`GET /api/skills` 时 `RegistryService.sync_local()`
自动对账源库目录：

```
GET /api/skills (routes.list_skills)
  ├─ registry.sync_local()   # 对账：发现新目录 → 登记
  ├─ registry.list_skills()  # 读登记表
  └─ 卡片: deployments + cache_missing + source_missing
```

启动时**不再**做 registry.json 一次性导入（`import_registry_json_if_empty` 已随
2026-09-22 工具链废弃删除）；`RegistryFile`/`RegistryAgent` 模型与
`backend/skill-manager/scripts/migrate_registry.py` 一并移除。

## sync_local() 契约

- 位置：`RegistryService.sync_local() -> int`（返回新增登记数）
- 触发：`list_skills` 路由每次调用（无缓存、无文件监听，本地毫秒级）
- 行为：
  1. `discover_local()` 扫描源库根（跳过 `.` 隐藏目录与
     `scripts/__pycache__/node_modules/logs/output`，目录名须符合 SkillId pattern）；
  2. **新目录**（id 不在登记表）→ upsert，name/summary 取自 SKILL.md frontmatter；
  3. **已登记条目一律不覆盖**（保护人工维护的 tags/summary/status/deprecated）；
  4. **目录缺失的已登记条目不处理**（保留），卡片显示 `source_missing`；
  5. 幂等：二次对账无新增返回 0。
- 失败降级：`OSError` / `RegistryValidationError` / `sqlite3.Error` → `logger.warning`，
  列表降级为现有登记，**绝不返 5xx**。

## frontmatter 解析契约

- `_parse_skill_md_frontmatter()`：识别 SKILL.md 头部 `---` 围栏块内
  `name` / `description` 单行标量（**零 YAML 依赖**，仅支持单行标量）；
- 无围栏 / 字段缺失 / 读取失败 → 返回空 dict，调用方降级（name=目录 id、summary=""）；
- 只读文件头 4096 字节，防超大 SKILL.md 拖慢扫描。

## SkillCard.source_missing

- 判定：`skill.source is LOCAL` 且 `(source_root / skill.path / "SKILL.md")` 非普通文件；
- github 来源恒 `False`（与 `cache_missing` 互不干扰）；
- 前端：`publishBlocked = cacheMissing || sourceMissing`，禁用目标 chips 与"加入队列"，
  提示"源库登记目录缺失，无法发布；恢复目录后自动解除"。

## 原 sync 工具链废弃（2026-09-22）

源库 `F:\personal-projects\skills` 的登记/发布工具链已整体废弃：

- 删除：`registry.json`、`registry.json.bak`、`sync-config.json`、
  `skill-agent-matrix.html`、`scripts/registry_loader.py` + `sync_*.py`、
  `tests/test_macro_skill_catalog.py`；
- skill-manager **不再读源库任何登记文件**；`registry.json` 的 agents 分配、
  tag 版本快照（`.cache/github-versions.json`）语义一并废弃；
- github 发布**固定检出远端 HEAD**（非 tag）——`remote_tags` 仅展示不选用；
- **遗留 junction**：`~/.claude/skills/git-commit-push`、`~/.codex/skills/git-commit-push`
  是工具链产物，继续存在由 claudecode/codex 使用，但 skill-manager 无
  `claudecode`/`codex` target，**不归其维护**。

## 相关坑

- **已登记条目绝不覆盖**：`sync_local` 只增不改——人工维护的 tags/summary/
  deprecated 在源目录变化后仍保留（2026-09-22 实现时的显式取舍）；
- **退役条目不自动删**：源目录被删后条目保留并 `source_missing`，防 NAS 瞬断误删；
  要移除只能走登记表清理（当前无此 API）；
- **新增自研 skill 零操作**：在源库建 `<skill>/SKILL.md`（frontmatter 写
  name/description），刷新管理台即自动登记；git-commit-push 这类已有 junction
  不在管理台发布能力内（claudecode/codex 目标不支持）；
- **junction vs symlink**：`Publisher` 用 `path.is_symlink()` 判定受管链接，
  junction 返回 False → 视为普通目录 → 拒绝覆盖/下架。若目标位置残留工具链
  junction，发布会 `blocked`，需先移除 junction 再让 Publisher 建 symlink。
