# 自研 skill 列表请求时对账同步 SQLite

## Goal

源库（SKILLS_SOURCE_ROOT）新增自研 skill 目录后，界面无需重启即可看到；源目录被删的已登记条目保留并在卡片上提示，不自动删除。

背景：当前界面真源是 SQLite `registry_skill` 表，源库更新不会同步进来（`import_registry_json_if_empty` 仅表空时一次性导入），`discover_local()` 已存在但未接到任何 API。用户确认的方案：**`GET /api/skills` 列表请求时惰性对账**（方案 B）。

## Requirements

- R1 对账时机：`GET /api/skills` 处理时先对账再返回——`discover_local()` 扫描源库，与登记表 diff，仅对 LOCAL 来源：
  - 新目录（登记表中不存在的 id）→ upsert 新条目；
  - 已登记且目录仍存在 → 不动（绝不覆盖人工维护的 summary/tags/status）；
  - 已登记但目录缺失 → 保留登记，不改写（删除语义见 R3）。
- R2 新条目元数据：解析目录内 `SKILL.md` frontmatter——`name` 填 `name`（缺失时用目录 id），`description` 填 `summary`（缺失时留空），`tags` 留空。frontmatter 缺失或解析失败不阻断登记（降级为 id + 空 summary）。
- R3 源缺失提示：`SkillCard` 新增 `source_missing: bool`（仅 LOCAL 来源可能为 True）。卡片显示"源缺失"类提示；不自动删除登记条目（防 NAS 瞬断误删）。GitHub 来源条目不受影响（现有 `cache_missing` 语义不变）。
- R4 降级：源库根不可达/扫描抛错时，列表仍正常返回现有登记条目，扫描失败只记 warning 日志，绝不 5xx。
- R5 幂等与性能：对账逻辑幂等；仅在有差异时写库；`os.walk` 每请求一次可接受（本地目录毫秒级），不做缓存、不做文件监听。
- R6 去除源库 registry.json 依赖（用户追加需求）：移除 skill-manager 对 `registry.json` 的全部读取——`import_registry_json_if_empty`、`RegistryFile`/`RegistryAgent` 模型、`REGISTRY_FILENAME` 常量及对应测试；全新环境首次 `GET /api/skills` 由 `sync_local()` 对账自动登记（元数据来自 frontmatter）。源库物理 `registry.json` 文件归源库 sync 工具链所有（`scripts/sync_*.py` 等仍在消费），**不在本次删除范围**。

## 非目标

- 不提供手动同步端点/按钮。
- 不做启动时同步（B 方案下冗余）。
- 不自动删除任何登记条目。
- 不改 GitHub 条目的登记/缓存/发布逻辑。
- 不修改 `import_registry_json_if_empty`（保留表空导入兼容）。

## Acceptance Criteria

- [ ] 源库新增含 `SKILL.md`（带 frontmatter name/description）的目录 → 刷新页面出现卡片，name/summary 与 frontmatter 一致。
- [ ] 新目录 `SKILL.md` 无 frontmatter 或解析失败 → 卡片仍出现，name=id，summary 空。
- [ ] 已登记 LOCAL 条目目录仍在 → 人工改过的 summary/tags/status 不被对账覆盖。
- [ ] 已登记 LOCAL 条目目录被删 → 卡片保留且带源缺失提示；目录恢复后提示消失。
- [ ] 源库根不可达时 → `GET /api/skills` 正常返回现有条目，无 5xx。
- [ ] GitHub 条目行为不变（cache_missing、更新检查、发布）。
- [ ] `uv run pytest tests/ -v` 全绿，含新增对账用例（新增/解析降级/不覆盖/缺失保留/扫描失败降级）。
- [ ] 前端 `pnpm build` 通过，卡片正确展示"自研"与"源缺失"状态。
- [ ] skill-manager 代码无任何 registry.json 读取逻辑（R6）；全新环境（空 SQLite）首次 `GET /api/skills` 即通过对账登记全部源库自研 skill，元数据来自 frontmatter；`uv run pytest tests/ -v` 全绿。
