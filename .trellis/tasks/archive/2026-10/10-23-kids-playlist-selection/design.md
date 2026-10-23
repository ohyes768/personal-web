# 技术设计：设备歌单手动选择合集 + 独立 tab

## 边界与不动点

- `DeviceCollections` 的生成事务模型（token/lease/两阶段校验/发布）不动，只改「候选如何被过滤」。
- 设备端契约不动：`/api/device/v1/collections`、`by-number`、快照 schema（`schema_version:1`、number/revision）。
- 下载、目录月度轮换（`Catalog.refresh`）、completions 台账不动。

## 后端

### 1. 候选清单进 `GET /api/collections` 响应

`main.py: collection_status()` 在 `collections.read()` 之外组装候选（新增 `Catalog.device_candidate_rows()`）：

```python
# Catalog 新增：只读查询，不加 begin immediate 长锁
def device_candidate_rows(self):
    with self.db() as con:
        rows = con.execute(
            "select a.title, j.status ... from albums a join jobs j "
            "on a.id=j.album_id where j.status='done' order by a.platform,a.title").fetchall()
    # → [{'folder': sanitize_filename(title), 'title': ..., 'source_id': ...}]
```

- 与 `device_candidates()` 同源同序（同一条 SQL），folder 冲突检测（同名目录）沿用其报错。
- completions 状态（complete/unconfirmed）由 `collections` 查询后补充进每项，前端据此渲染 unconfirmed 标记。
- 响应形如 `{snapshot, generation, candidates}`；`candidates` 每项 `{folder, title, confirmed}`。

注意：`device_candidates()` 是 `begin immediate` 写锁的 contextmanager，专供生成事务用；`device_candidate_rows()` 是独立只读方法，GET 路径不碰写锁。

### 2. `POST /api/collections/generate` 接受选择

- Body（可选）：`{"folders": ["<folder>", ...]}`，元素为候选 folder（= `sanitize_filename(title)`）。
- 语义约定：
  - body 缺省 / `folders` 为 null → 全部候选（兼容现状）。
  - `folders: []` → 422「请至少选择一个合集」。
  - 含未知 folder → 422，报出未知项（显式失败优于静默忽略，防止前端状态漂移生成意外歌单）。
- 校验在 `main.py` 路由层完成（对照 `device_candidate_rows()` 的 folder 集合），通过的 folder 集合作为参数传给 `collections.start(prepare, selected_folders)`。
- `DeviceCollections._generate()`：`sources` 过滤为 `selected_folders`（None = 不过滤）。被过滤掉的合集不进 items 也不进 skipped；其余校验、跳过、发布逻辑逐行不动。
- 生成期间合集列表一致性检查（`current_sources != sources`）改为只对比选中集合，避免未选合集的无关变化导致生成失败。

### 3. 数据流

```
GET  /api/collections          → {snapshot, generation, candidates[]}
POST /api/collections/generate {folders?} → 过滤后的 candidates → _generate → publication
设备端 API                      → 不变
```

## 前端

### 4. Tab 结构（query param 方案）

- `page.tsx` 顶部 tab 条：「本月精选」`?tab=catalog`（默认）/「设备歌单」`?tab=playlist`。
- 用 `useSearchParams` 读取、路由 push 切换；SSP/SSR 无要求（页面本就是 client component）。
- `<DevicePlaylist/>` 从首页主体移入 `tab=playlist` 分支；专辑目录/获取最新/下载留在本月精选 tab。
- `layout.tsx`、rewrites、basePath 不动。

### 5. 候选勾选清单（device-playlist.tsx）

- 读取 `state.candidates`，`useState<Set<string>>` 维护勾选，初始 = 全部 folder（有主见的默认值=全选；candidates 变化时只增量并入新 folder，不清空用户已勾的）。
- 每行：复选框 + 合集名 + （unconfirmed 时）「未确认」标记。
- 生成：POST `{folders: [...checked]}`；清单为空或全不选时前端拦截提示，不发请求。
- 生成中（running）禁用复选框，保持现有 2s 轮询。
- skipped 确认流程原样保留。

### 6. 样式

- `globals.css` 增加 tab 条与勾选清单行样式，沿用现有暖白纸感/数据密度基调。

## 权衡记录

- **tab 用 query param 而非新路由**：单 page.tsx 的极简结构，新路由要引入目录与布局改动，收益低。
- **未知 folder 422 而非忽略**：显式失败避免「前端旧勾选状态 × 后端候选已轮换」时静默生成错位歌单。
- **不持久化勾选**：MVP 默认全选已覆盖主路径（生成时临时排除少数合集），持久化引入过期 folder 清理问题，不做。

## 回滚

- 后端：generate 的 folders 参数为可选叠加，回滚 = 前端不传 folders 即回到全量行为；candidates 字段是响应新增键，旧前端忽略。
- 前端：tab 拆分是纯客户端结构改动，revert 单 commit 即可。
