# 调研：skill-manager 标签体系 ↔ service-manager 现状

> 目的：搞清 skill-manager 的标签怎么做的（可照搬的部分），service-manager 现在缺什么。

## A. skill-manager 的标签体系（全貌）

### A1. 模型与存储

| 位置 | 内容 |
|------|------|
| `backend/skill-manager/src/models.py` | `Tag = Annotated[str, Field(min_length=1, max_length=40)]`；`RegistrySkill.tags: list[Tag] = []`；PATCH 请求体 `SkillTagsUpdate.tags: list[Tag]` |
| `backend/skill-manager/src/db.py` | `registry_skill.tags TEXT NOT NULL DEFAULT '[]'`（JSON 数组），写入 `json.dumps(tags, ensure_ascii=False)`，读取 `json.loads(row["tags"])` |

要点：标签就是**字符串数组**，存 JSON，没有独立标签表、没有标签 ID。

### A2. 写入路径（全量替换）

`PATCH /api/skills/{skill_id}/tags` → `RegistryService.update_skill_tags(skill_id, tags)`：

```python
updated = skill.model_copy(update={"tags": sorted(set(tags))})   # 去重 + 排序
self.store.upsert_registry_skill(updated)
```

docstring 里两个要点：
- **刻意绕过 `upsert()` 的 `_check_path`**：标签维护不依赖源目录存在（源没了的 local 条目照样能改标签）。
- 未知 id → `RegistryValidationError`（不是静默成功）。

### A3. 候选标签（前端算）

`apps/skill-manager/src/lib/tagCandidates.ts`：

```ts
export function getTagCandidates(allTags: string[], skillTags: string[], selected: string[]): string[] {
  return Array.from(new Set([...allTags, ...skillTags, ...selected])).sort();
}
```

候选 = **全库标签并集** ∪ 本条目已有标签 ∪ 当前选中，去重排序。后端**不提供**「标签字典」接口。

### A4. 编辑弹窗（`EditSkillTagsDialog.tsx`）

- 已有标签渲染成一排**药丸按钮**，点一下 toggle（勾选 / 取消），选中态是深色实心。
- 下方一个输入框 + 「添加」按钮，**回车也能添加**；校验：空串忽略、长度上限 40、重复勾选报错「该标签已勾选」。
- 保存时 `onSave([...selected].sort())`——全量替换语义。

### A5. 筛选栏（`SkillFilters.tsx`）

```ts
export interface FilterState {
  query: string;
  tags: string[];        // 多选
  deployment: 'all' | 'installed' | 'uninstalled';
  update: 'all' | 'has_update' | 'no_update';
}
```

- 搜索框 + 状态下拉 + **一排标签药丸按钮**（点一下选中/取消），下方「清除标签」一键清空。
- 筛选状态**完全在前端**（`FilterState` 是 useState），不进 URL。

### A6. 过滤语义（`SourceWorkspace.applyFilters`）

```ts
if (filters.tags.some((tag) => !skill.tags.includes(tag))) return false;
```

**多选标签是 AND**：勾了 2 个标签，只显示同时具备这两个的服务。

### A7. 卡片展示（`SkillPool.tsx`）

每张卡片底部显示自己的标签药丸 + 一个**铅笔图标按钮**（`aria-label="编辑标签"`）→ 打开编辑弹窗。没有标签的卡片给一个空心药丸按钮，也能点开编辑。

## B. service-manager 现状

### B1. 后端已经有的（不用重做）

| 能力 | 位置 | 说明 |
|------|------|------|
| 存储 | `backend/service-manager/src/db.py` | `services.tags TEXT NOT NULL DEFAULT '[]'`（JSON 数组） |
| 写入 | `src/models.py` `ServiceCreate.tags` / `ServicePatch.tags` | PATCH 是**全量替换**；≤20 个 |
| 校验 | `src/models.py` `clean_tags()` | strip、丢空串、**长度 ≤32**、去重但**保留原序** |
| 单标签过滤 | `src/registry.py` `list_services(tag=...)` | `s.tags LIKE '%"tag"%'`——带引号匹配，`"a"` 不会误命中 `"ab"` |
| 搜索 | 同上 `query` | 已把 `s.tags` 纳入搜索字段 |
| API 参数 | `apps/service-manager/lib/api.ts` `listServices({tag?})` | 前端**没传过**这个参数 |

### B2. 前端缺的（这次要做的）

1. **标签不能维护**：详情页「编辑信息」里 tags 是个逗号分隔的文本框（`draft.tags`），要手打全拼、写错没有提示。
2. **标签不能筛选**：列表页把 tags 渲染成纯文本 `tags.join(" · ")`，点不了；工具栏只有「全部分类」下拉。
3. **没有标签候选来源**：前端可以照 skill-manager 从全量列表算并集（`page_size=100` 已经把全部服务拉回来了）。
4. **多选筛选后端不支持**：后端 `tag` 参数只收单个标签。

### B3. 与「分类 / 归属」的关系

service-manager 现在有三个正交的人工字段：

| 字段 | 形态 | 语义 | 谁能改 |
|------|------|------|------|
| `category` 分类 | 单选自由文本 | 大类（金融 / 媒体 / 基础设施…） | 详情页编辑 |
| `ownership` 归属 | 二选一 | 我维护的 / 别人的（列表分组） | 列表行下拉、详情页下拉 |
| `tags` 标签 | 多选自由文本 | 用途 / 技术栈 / 形态等横切维度 | **缺交互** |

标签**不替代**归属（归属决定分组，标签决定筛选）；分类与标签有重叠（分类可以看作一类固定标签）。

## C. 可照搬 / 需要决策的点

| 维度 | skill-manager | service-manager | 建议 |
|------|---------------|-----------------|------|
| 标签存法 | JSON 数组（复用条目字段） | 已经是 JSON 数组 | **沿用现字段**，不引入独立标签表 |
| 长度上限 | 40 | 32 | 保持 32（后端既有契约，不为对齐而改） |
| 保存顺序 | `sorted(set())` | `clean_tags()` 保序 | 改成排序，与 skill-manager 一致（筛选栏显示顺序才稳定）——**需确认是否算行为变更** |
| 编辑入口 | 卡片铅笔 → 弹窗 | 只有详情页表单 | 加卡片铅笔弹窗；详情页表单保留（不删） |
| 候选来源 | 前端并集 | 同 | 前端并集，不加后端接口 |
| 多选语义 | AND | 后端只支持单 tag | 前端过滤（数据已在手）；或后端加 `tags=a,b` 参数 |
| 筛选状态 | 前端 useState | 同 | 前端；不进 URL |

## D. 相关文件清单（实现时要动/要读）

**读**：
- `apps/skill-manager/src/components/EditSkillTagsDialog.tsx`（弹窗原型）
- `apps/skill-manager/src/components/SkillFilters.tsx`（筛选栏原型）
- `apps/skill-manager/src/lib/tagCandidates.ts`（候选算法）
- `apps/skill-manager/src/components/SourceWorkspace.tsx`（`applyFilters` 语义）
- `backend/skill-manager/src/services/registry.py`（`update_skill_tags` 语义：全量替换、排序去重）

**改**：
- `apps/service-manager/app/page.tsx`（列表页：标签药丸 + 筛选栏 + 编辑弹窗；**删「全部分类」下拉**）
- `apps/service-manager/app/service/[id]/page.tsx`（详情页标签展示/编辑；**删分类输入框**）
- `apps/service-manager/app/discovery/page.tsx`（**删导入表单的分类输入框**）
- `apps/service-manager/components/`（新增 `TagEditor` / `TagFilterBar` / `TagBadge`）
- `apps/service-manager/lib/api.ts`（类型去 `category`、`listServices` 去 `category` 参数）
- `backend/service-manager/src/models.py`（`clean_tags` 排序；删 5 处 `category` 字段）
- `backend/service-manager/src/registry.py`（`list_services` 去掉分类过滤；新增分类退役迁移）
- `backend/service-manager/src/db.py`（`_SCHEMA` 去 category；加 DROP COLUMN 迁移）
- `backend/service-manager/src/backup.py`（导出改显式选列；恢复 INSERT 去 category）
- `backend/service-manager/src/discovery.py`（INSERT 去 category）
- `backend/service-manager/src/api/routes.py`（删 `category` 查询参数）
- `apps/service-manager/e2e/service-manager.spec.ts`（标签维护 + 筛选用例；去掉 `category` 参数）

**spec**：
- `.trellis/spec/apps/service-manager/frontend/index.md`
- `.trellis/spec/backend/service-manager/backend/index.md`

## E. 分类退役的现状数据与影响面（Q4 补充调研）

### E1. 现有分类值分布

| 分类 | 条数 |
|------|-----|
| 工具 | 9 |
| 生活 | 6 |
| 金融 | 5 |
| 内容 | 3 |
| 媒体 | 1 |

24 条服务**全部**有分类值 → 迁移为标签后，这 5 个值会成为候选词表的一部分。

### E2. 现有标签词表（22 个）

`media(4) public(3) infra(3) family(2) rss(2) fund housing index kids macro skill hermes cron self photo home stock search ai monitor tool gateway dns`

迁移后候选词表 = 22 + 5 = **27 个**。

### E3. `category` 引用点全量清单

| 层 | 位置 | 数量 |
|----|------|-----|
| 前端 | `app/page.tsx`（状态下拉、请求参数、候选分类、行内显示） | 5 |
| 前端 | `app/service/[id]/page.tsx`（draft、编辑表单） | 4 |
| 前端 | `app/discovery/page.tsx`（导入表单） | 3 |
| 前端 | `lib/api.ts`（两个类型 + 请求参数） | 3 |
| 前端 | `e2e/service-manager.spec.ts` | 2 |
| 后端 | `src/models.py`（5 个字段） | 5 |
| 后端 | `src/registry.py`（行转模型、INSERT、列表过滤、搜索子句、PATCH） | 6 |
| 后端 | `src/db.py`（`_SCHEMA`） | 1 |
| 后端 | `src/backup.py`（恢复 INSERT） | 1 |
| 后端 | `src/discovery.py`（INSERT） | 1 |
| 后端 | `src/api/routes.py`（查询参数） | 1 |
| 测试 | `test_registry.py` / `test_backup.py` | 4 |

合计约 36 处引用点，分布在前后端 + 备份 + 测试。

### E4. SQLite `DROP COLUMN` 可行性

- 需要 SQLite ≥ 3.35（2021-03）。
- 本机 3.45.1 ✅，容器（python:3.12-slim）3.46.1 ✅。
- `services.category` **无索引、无外键引用**（唯一索引是 `service_components.service_id`）→ 可 DROP。
- 迁移必须**先转标签再删列**；两步都要幂等（列不存在 / 值为空时直接跳过）。
