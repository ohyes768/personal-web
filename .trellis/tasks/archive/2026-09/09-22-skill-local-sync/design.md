# 技术设计：自研 skill 列表请求时对账同步

## 1. 分层与职责

对账逻辑放进 `RegistryService`（登记真源唯一读写入口），路由层只调用与降级：

```
GET /api/skills (routes.list_skills)
  ├─ registry.sync_local()          # 新增：对账，失败仅 warning，不阻断
  ├─ registry.list_skills()          # 现状不变
  └─ _build_card(..., source_missing=...)  # 新增参数
```

### RegistryService 新增

- `sync_local() -> int`：返回新增条目数。
  1. `discovered = {s.id: s for s in self.discover_local()}`；
  2. `existing = {s.id for s in self.list_skills() if s.source is SkillSource.LOCAL}`；
  3. `new_ids = discovered - existing`：对每个新 id，用 `_parse_skill_md_frontmatter` 的结果补 `name`/`summary` 后 `upsert`（复用现有 `_validated` 路径校验）；
  4. 已存在的条目一律不 upsert（绝不覆盖人工维护的 summary/tags/status/deprecated）；
  5. 目录缺失的已登记条目不处理（保留，删除语义为零操作）。
- `_parse_skill_md_frontmatter(skill_dir) -> dict`：手写轻量解析，零新依赖
  （pyproject 无 pyyaml；name/description 均为单行标量，无需完整 YAML）：
  - 仅识别文件头部 `---` 围栏块内 `key: value` 行，取 `name`、`description`；
  - 无围栏 / 解析异常 / 字段缺失 → 返回空 dict，调用方降级（name=id，summary=""）；
  - 任何 OSError 视为无 frontmatter。

### discover_local 微调

扫描时对每个候选读 frontmatter 放入候选对象（避免 sync 阶段二次 IO）——候选仍为
`RegistrySkill`，`name`/`summary` 直接带解析结果。函数签名不变。

## 2. API 契约变化

`SkillCard` 新增字段（向后兼容，默认值）：

```python
# 本环境源库中登记目录缺失（LOCAL 来源专用；github 来源恒 False）
source_missing: bool = False
```

判定：`_build_card` 时 LOCAL 来源且 `(source_root / skill.path / "SKILL.md")` 不是
普通文件 → True。对账之后该状态天然与磁盘一致。

GitHub 条目的 `cache_missing`、`update`、部署徽章逻辑全部不动。

## 3. 前端变化

- `lib/types.ts`：`SkillCard` 加 `source_missing: boolean`（可选或默认 false）。
- `SkillPool.tsx` 徽章区：`source_missing` 时显示灰色/琥珀色"源缺失"徽章
  （文案对齐 `link_missing` 的提示风格），并禁用"加入队列"按钮（发布必然
  blocked，对齐 `cache_missing` 的禁用模式）；已部署徽章照常显示。

## 4. 错误与降级

- `sync_local()` 内 `discover_local()` 抛 `OSError`（源库根不可达/NAS 瞬断）→
  `list_skills` 捕获，`logger.warning`，继续返回现有登记；绝不 5xx。
- 单个候选 frontmatter 解析失败不影响该候选登记（降级元数据）。
- upsert 失败（如路径穿越校验拒绝，理论不可达——discover 已限定在源库根内）→
  同样捕获记日志，不阻断列表。

## 5. 并发与性能

- 路由为 sync def，FastAPI 线程池执行，与现有 store 用法同模式，无新增并发面。
- 每请求一次 `os.walk` + 命中候选读一次 SKILL.md 头部：本地目录毫秒级，可接受。
- 无缓存、无文件监听（非目标）。

## 6. 兼容与回滚

- `source_missing` 带默认值，API 消费方无需同步升级。
- `import_registry_json_if_empty` 保持不变（表空导入仍生效，先导入后对账可共存）。
- 回滚 = revert 代码；SQLite 无 schema 变更、无数据迁移。

## 7. 测试策略（backend/skill-manager/tests/）

新文件 `test_local_sync.py`（fixture 模式参照 `test_registry.py`：tmp_path 造源库根）：

1. 新目录含 frontmatter → 列表出现卡片，name/summary 正确；
2. 无 frontmatter / SKILL.md 无围栏 → name=id，summary=""，卡片仍出现；
3. 已登记条目人工 summary/tags → sync 后不被覆盖；
4. 目录删除 → 条目保留，`source_missing=True`；目录恢复 → False；
5. 源库根不可达（source_root 指向不存在路径）→ 列表正常返回，无异常上抛；
6. github 条目不受 sync 影响（既有 test_api 断言继续绿）。

前端：`pnpm build` 通过 + 浏览器手验卡片徽章（源缺失态用临时改名目录模拟）。
