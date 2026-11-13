# 实施计划：service-manager 标签体系

> 配套 `prd.md` / `design.md`。每步做完就跑对应验证命令；绿灯再进下一步。

## 步骤 0 · 前置

- [x] 确认 Q1–Q4 四个待定项（AND / 前端筛 / 排序 / 砍分类），回填 `design.md` §8 与 `prd.md`
- [ ] 确认没有活跃 Trellis 任务冲突：`python3 ./.trellis/scripts/task.py current --source`
- [ ] 基线绿灯（改之前先确认不是既有红灯）：
  ```bash
  cd backend/service-manager && .venv/bin/python -m pytest tests/ -q
  cd apps/service-manager && pnpm exec tsc --noEmit && pnpm lint
  ```

## 步骤 1 · 后端：标签排序（Q3）

- [ ] `backend/service-manager/src/models.py`：`clean_tags()` 改为 `sorted(set(...))`，docstring 写清「去重 + 排序，与 skill-manager 一致」
- [ ] `backend/service-manager/src/registry.py`：确认 `list_services(tag=...)` 行为不变（单标签 LIKE 匹配）
- [ ] 验证：
  ```bash
  cd backend/service-manager && .venv/bin/python -m pytest tests/ -q
  ```
- 回滚点：仅 `models.py` 一个函数，单独可还原

## 步骤 2 · 后端：分类退役（Q4，先转标签后删列）

- [ ] `src/registry.py`：新增 `migrate_category_to_tags()`——读出每条服务的 `(category, tags)`，`category` 非空则并入 tags（排序去重）回写；**全部成功后再删列**
- [ ] `src/db.py`：加迁移——列存在则 `ALTER TABLE services DROP COLUMN category`（SQLite ≥3.35；本机 3.45.1 / 容器 3.46.1）；`_SCHEMA` 去掉 category 列
- [ ] `src/main.py`：`build_app` 里调用迁移（与 `backfill_ownership` 同位置，幂等）
- [ ] 清理引用：`src/models.py`（5 处字段）、`src/registry.py`（INSERT / 过滤参数 / 搜索子句）、`src/discovery.py`（INSERT）、`src/backup.py`（导出改**显式选列**、恢复 INSERT 去掉 category）、`src/api/routes.py`（`category` 查询参数）
- [ ] 后端测试：去掉 `test_registry.py` / `test_backup.py` 里的 `category=`；新增迁移用例（值转成标签、幂等重跑、旧备份恢复不报错）
- [ ] 验证：`cd backend/service-manager && .venv/bin/python -m pytest tests/ -q`
- 回滚点：**这一步不可逆**（列删掉后分类值只存在于标签里）；上线前先在副本库跑一遍并核对条数与标签

## 步骤 3 · 前端：标签基础件（纯函数 + 组件骨架）

- [ ] `apps/service-manager/lib/tagCandidates.ts`：`getTagCandidates`（照搬 skill-manager 语义）
- [ ] `apps/service-manager/lib/tagFilter.ts`：`matchesTags`（AND）
- [ ] `apps/service-manager/components/TagBadge.tsx`：药丸展示（可点击触发筛选 / 打开编辑）
- [ ] `apps/service-manager/components/TagEditor.tsx`：弹窗（勾选 + 新建 + 校验 + 保存）
- [ ] `apps/service-manager/components/TagFilterBar.tsx`：药丸筛选排 + 清除
- [ ] 验证：`pnpm exec tsc --noEmit && pnpm lint`

## 步骤 4 · 列表页接入（含分类入口下线）

- [ ] `app/page.tsx`：
  - [ ] 状态 `tagFilter: string[]` / `editingTagsFor: ServiceListItem | null`
  - [ ] `allTags` 由 `items` 派生（**来自全量，不是当前 tab**）
  - [ ] 工具栏插入 `TagFilterBar`；**删除「全部分类」下拉**
  - [ ] 每行渲染标签药丸 + 「编辑标签」按钮；**删除行内分类文本**
  - [ ] 保存后**就地更新** `items`（含 `revision` 用后端返回值覆盖，否则下次 PATCH 409）
  - [ ] 筛选链：归属分组 → 搜索 → 标签（分类维度消失）
- [ ] `lib/api.ts`：类型去掉 `category`，`listServices` 去掉 `category` 参数
- [ ] 验证：`pnpm exec tsc --noEmit && pnpm lint`；手动点一遍（改标签 / 筛选 / 清除 / 与搜索叠加）

## 步骤 5 · 详情页与发现导入接入

- [ ] `app/service/[id]/page.tsx`：显示标签药丸（点击跳列表并筛选）；**编辑表单去掉「分类」输入框**
- [ ] `app/discovery/page.tsx`：**导入表单去掉「分类」输入框**
- [ ] 验证：手动（详情页改完回列表可见）

## 步骤 6 · e2e

- [ ] `e2e/service-manager.spec.ts`：
  - [ ] 改掉用例里的 `category: "e2e"` 参数
  - [ ] 新增：打开标签弹窗 → 勾选已有标签 + 新建一个 → 保存 → 列表行立即显示
  - [ ] 新增：点标签药丸筛选 → 只剩匹配的服务 → 「清除标签」恢复
  - [ ] 新增：界面上没有「分类」入口（列表页 / 详情页 / 发现导入）
  - [ ] 375px 下弹窗可操作、无横向滚动
- [ ] 全量：`pnpm exec playwright test`（desktop + mobile）
- [ ] 失败时先看是不是既有红灯（基线见步骤 0）

## 步骤 7 · spec 更新（Phase 3.3）

- [ ] `.trellis/spec/apps/service-manager/frontend/index.md`：标签维护与筛选的交互约束（药丸语义、AND、候选并集、375px 约束）；**分类退役**说明
- [ ] `.trellis/spec/backend/service-manager/backend/index.md`：标签契约（≤32 字符、≤20 个、全量替换、排序去重）；**分类退役**（迁移顺序、不可逆、旧备份兼容）
- [ ] 若 Q3 落地为行为变更，在 spec 里明确写「标签按字典序保存」

## 步骤 8 · 收尾（Phase 3.4）

- [ ] `git status --porcelain` 盘点脏文件，区分「本次改的」与「别人的/上一轮的」
- [ ] 拟提交计划 → 用户确认 → 分批提交（**不 push**）
- [ ] 提醒用户跑 `/trellis:finish-work`

## 风险与回滚

| 风险 | 处置 |
|------|------|
| 改坏既有标签顺序（Q3 行为变更） | 单独提交、spec 记一笔；回滚只需还原 `clean_tags` |
| **分类退役不可逆**（列删掉后分类值只在标签里） | 先转标签后删列；上线前在副本库跑一遍并核对条数与标签；值可从标签反推 |
| 前端筛选与服务数超 `page_size` 不一致 | 当前 24 条 / 上限 100，暂时无关；超了要在 spec 写明 |
| 与别人同时改 `apps/service-manager` | 动手前先 `git status` 看脏文件，别覆盖别人的改动 |
