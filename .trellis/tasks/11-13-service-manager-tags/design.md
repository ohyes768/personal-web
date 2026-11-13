# 设计：service-manager 标签体系

> 配套 `prd.md`。本文只讲**怎么做**：组件边界、数据流、交互契约、兼容与取舍。

## 1. 总体形态

照搬 skill-manager 的三个构件，落到 service-manager：

| skill-manager | service-manager 对应 | 作用 |
|--------------|---------------------|------|
| `TagCandidates`（`getTagCandidates`） | `lib/tagCandidates.ts` 同名同语义 | 算候选标签并集 |
| `EditSkillTagsDialog` | `components/TagEditor.tsx` | 弹窗：勾选 + 新建 + 保存 |
| `SkillFilters` 里的药丸排 | `components/TagFilterBar.tsx` | 药丸多选筛选 + 清除 |
| `applyFilters` 的 AND 语义 | `lib/tagFilter.ts` 的 `matchesTags` | 前端过滤 |

**不动数据模型**：标签继续用 `services.tags`（JSON 数组）；后端 PATCH 已是全量替换语义；**不新增后端接口**。

## 2. 数据流

```
GET /api/services?page_size=100
        │  全量服务（items[].tags）
        ▼
  前端派生 ── allTags = unique(所有 item.tags)      ← 候选词表（不落库）
             ├─ TagFilterBar（多选，AND）
             └─ TagEditor（每行铅笔按钮）
                    │ 勾选/新建 → sorted(tags)
                    ▼
              PATCH /api/services/{id} { tags, revision }
                    │ 200 → 就地更新本地 items（不必整表重拉）
                    │ 409 → 提示「记录已被修改，请刷新后重试」并重拉
                    ▼
              人工表 services.tags（Docker 不受影响）
```

筛选链：**归属分组 → 搜索 → 分类 → 标签**，四者叠加，标签最后过滤（AND）。

## 3. 组件契约

### 3.1 `components/TagEditor.tsx`

```tsx
interface TagEditorProps {
  tags: string[];              // 本条当前标签
  allTags: string[];           // 全库并集（候选）
  busy?: boolean;
  error?: string;
  onSave: (tags: string[]) => void;
  onClose: () => void;
}
```

- 弹窗容器：`role="dialog" aria-modal="true"`，标题「编辑标签 · {服务名}」。
- 候选区：药丸按钮列表，选中态与未选中态**颜色之外还有文字状态**（选中加 `aria-pressed="true"`）。
- 新建区：输入框（`maxLength=32`）+「添加」按钮，**回车也能添加**。
- 校验（照抄 skill-manager 口径）：
  - 空串 → 忽略
  - 超过 32 字符 → 「标签最长 32 个字符」
  - 与已勾选重复 → 「该标签已勾选」
- 保存：`onSave([...selected].sort())`；保存期间禁用输入与按钮（`busy`）。
- 关闭：`取消` 按钮 + `Esc`；关闭不丢已勾选（下次打开重新读 props）。

### 3.2 `components/TagFilterBar.tsx`

```tsx
interface TagFilterBarProps {
  allTags: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}
```

- 一排药丸按钮，点一下 toggle 选中/取消；`aria-pressed` 标状态。
- 选中非空时右侧出现「清除标签」（一键清空）。
- `allTags` 为空 → **整条不渲染**（不出现空药丸排）。
- 药丸排可换行（`flex-wrap`），375px 下纵向堆叠，不产生横向滚动。

### 3.3 `components/TagBadge.tsx`（列表行展示）

- 展示本条标签的小药丸；点击药丸 = **直接按该标签筛选**（少一次找筛选栏的动作）。
- 无标签时给一个虚线药丸「+ 标签」，点开编辑弹窗。

### 3.4 `lib/tagCandidates.ts` / `lib/tagFilter.ts`

```ts
getTagCandidates(allTags: string[], ownTags: string[], selected: string[]): string[]
  = Array.from(new Set([...allTags, ...ownTags, ...selected])).sort()

matchesTags(itemTags: string[], selected: string[]): boolean
  = selected.every((tag) => itemTags.includes(tag))     // AND
```

## 4. 页面改动

### 4.1 列表页 `app/page.tsx`

- 新增状态：`tagFilter: string[]`、`editingTagsFor: ServiceListItem | null`。
- `allTags` 由 `items` 派生（`useMemo`）；**注意归属分组切换不影响候选词表**（词表来自全量 `items`，不是当前 tab）。
- 行内标签列：每行显示 `TagBadge` 列表 + 「编辑标签」铅笔按钮。
- 工具栏：搜索框 / 分类下拉 / 标签筛选栏 / 扫描容器 / 巡检。
- 保存标签后就地更新 `items`（不整表重拉，避免筛选态跳动）：
  ```ts
  setItems((prev) => prev.map((it) => (it.id === target.id ? { ...it, tags } : it)));
  ```
  同时 `revision` 也要更新（否则下一次 PATCH 会 409）——**关键点**：PATCH 成功后用后端返回的 `ServiceDetail.revision` 覆盖本地 revision。

### 4.2 详情页 `app/service/[id]/page.tsx`

- 组件区上方显示本条标签（药丸），点药丸 = 跳回列表并按该标签筛选。
- 「编辑信息」表单里的标签字段**保留**（逗号分隔文本框），与弹窗并存；两边都写同一个 `tags` 字段。

## 5. 后端

### 5.1 标签相关改动

| 改动 | 理由 | 风险 |
|------|------|------|
| `clean_tags()` 改为 `sorted(set(...))` | 与 skill-manager 一致；药丸栏按字典序显示才稳定 | **行为变更**：已有数据的标签顺序会变（无语义影响）→ 需在 spec 记一笔 |
| `GET /api/services?tag=x` 保持单标签 | 前端做多选过滤，后端不必加参数 | 无 |
| 新增接口 | **无** | — |

后端 `PATCH /api/services/{id}` 已是全量替换 `tags`，前端直接发完整数组即可；`tags` 最多 20 个、单标签 ≤32 字符由 pydantic 兜底（超限 → 400 + `field_errors`，前端要显示出来）。

### 5.2 分类退役（Q4 确认：砍掉）

**迁移顺序：先转标签，后删列**（中途失败不丢数据）。

```
启动时 registry.migrate_category_to_tags()
   ├─ 读出所有 services 的 (id, category, tags)
   ├─ category 非空 → tags ∪ {category} → 排序去重 → 回写
   └─ 全部回写成功后，再 ALTER TABLE services DROP COLUMN category
```

- **幂等**：迁移过的行 `category` 已清空 / 列已不存在 → 第二次运行什么都不做。
- **不可逆**：列删掉后原分类值只以标签形式存在（可从标签反推，但不再是独立字段）→ 写进 spec。
- SQLite 版本要求：`DROP COLUMN` 需 ≥ 3.35。本机 3.45.1、容器 3.46.1 ✅。
- 列有索引/外键引用时不能 DROP：`services.category` 无索引 ✅。

**要清理的引用点**（全量清单，调研已核对）：

| 位置 | 改动 |
|------|------|
| `src/models.py` | `ServiceCreate.category` / `ServicePatch.category` / `ServiceListItem.category` / `ServiceDetail.category` / 发现导入模型里的 `category` 全部删除 |
| `src/registry.py` | INSERT 语句去掉 category 列；`list_services` 的 `category` 过滤参数与 `s.category = ?` 子句删除；搜索字段里去掉 `lower(s.category)` |
| `src/db.py` | `_SCHEMA` 去掉 category 列；新增 DROP COLUMN 迁移 |
| `src/discovery.py` | 建服务 INSERT 去掉 category |
| `src/backup.py` | 导出 `services` 改为**显式选列**（不再 `SELECT *`，避免带出已删字段）；恢复 INSERT 去掉 category（旧备份里的 `category` 键被忽略） |
| `src/api/routes.py` | `GET /services` 的 `category` 查询参数删除 |
| 前端 `lib/api.ts` | 类型与 `listServices({category})` 参数删除 |
| 前端 `app/page.tsx` | 「全部分类」下拉删除；行内分类文本删除 |
| 前端 `app/service/[id]/page.tsx` | 编辑表单的「分类」输入框删除 |
| 前端 `app/discovery/page.tsx` | 导入表单的「分类」输入框删除 |
| 后端 tests | `test_registry.py` / `test_backup.py` 里的 `category=` 参数去掉；新增迁移用例 |

**迁移后的标签词表**：原 22 个标签（media/public/infra/family/rss…）+ 5 个分类值（工具/生活/金融/内容/媒体）= 27 个候选标签。

## 6. 取舍与已知代价

1. **前端筛选**：台账规模（24 条，page_size=100）远小于单页上限，全量在手；后端加多标签参数要连带处理分页计数，收益不抵复杂度。代价：服务数超过 `page_size` 时筛选只覆盖当前页——**当前上限 100 条，够用**；若将来超了要在 spec 里写明。
2. **不做独立标签表**：不能重命名/合并/统计使用数；换来的好处是零迁移、零新接口、备份格式不变。
3. **AND 语义**（Q1 已确认）：勾 2 个标签只剩 2 个都有的服务，符合「精确定位」；代价是想看「A 或 B」得取消勾选。
4. **分类退役**（Q4 已确认）：统一用标签，少一个正交维度；代价是原来的单选大类变成了「众多标签之一」，筛选栏里会多 5 个分类来源的标签（工具/生活/金融/内容/媒体）。

## 7. 兼容与回滚

- 无 schema 变更 → 备份导出格式不变，旧备份仍可恢复。
- 前端改动全在 `apps/service-manager`，回滚 = 还原前端文件；后端只有 `clean_tags` 排序这一处行为变更，可单独回滚。
- 不触碰 Docker 只读边界与检查口径（spec §2.1 / §2.3 的硬边界不受影响）。

## 8. 已确认的结论（2026-11-13）

| # | 结论 | 影响的章节 |
|---|------|-----------|
| Q1 | **AND**：多选标签同时具备才算命中 | §3.4 `matchesTags`、§6.3 |
| Q2 | **前端筛选**：不新增后端筛选参数 | §1 数据流、§5.1 |
| Q3 | **排序去重**：`clean_tags()` 改为 `sorted(set(...))` | §5.1 |
| Q4 | **砍掉 `category`**：值迁移为标签，字段与界面入口全部下线 | §5.2、§6.4 |

§6 的取舍相应更新：取舍 3（AND 语义）不再是待定；取舍 4 从「分类与标签并存」改为「分类已退役，统一用标签」。
