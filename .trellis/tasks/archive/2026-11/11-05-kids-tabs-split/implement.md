# 实现清单：榜单与手动导入拆分为独立 tab

> 关联：`prd.md`。后端 `albums.source`（chart / manual）已具备，本任务为纯前端拆分。

## 实施顺序

### 前端 apps/kids-catalog

- [x] 1. `app/page.tsx`：新增 `Tab` 类型 `"catalog" | "manual" | "playlist"`；
      URL `?tab=` 解析（`manual` / `playlist`，其余回落 `catalog`），`switchTab` 用
      `router.push(`${pathname}?tab=${next}`, {scroll:false})` 保持滚动位置。
- [x] 2. `app/page.tsx`：专辑列表按 `source` 分流——`chartAlbums`（`source==='chart'`）
      与 `manualAlbums`（`source==='manual'`）两个数组，专辑卡片 `albumCard(x)` 在两个 tab 间复用。
- [x] 3. `app/page.tsx`：导航区渲染三个 tab 按钮（本月精选 / 手动添加 / 设备歌单），
      `aria-current` 标记当前 tab。
- [x] 4. `app/page.tsx`：手动导入表单（粘贴链接 + 获取按钮）移入「手动添加」tab；
      导入成功后停留在手动 tab 并展示 `message` 提示。
- [x] 5. `app/page.tsx`：标题与副标题按 tab 切换；「获取最新」按钮与月度时间戳
      （`N年N月精选` / `更新于`）仅在「本月精选」tab 渲染。
- [x] 6. `app/page.tsx`：空状态文案分 tab 适配——本月精选提示点「获取最新」，
      手动添加提示粘贴链接导入。
- [x] 7. 「手动添加」tab 内不渲染「手动添加」徽章（该 tab 全部卡片均为手动来源，徽章冗余）；
      下载 / 重试 / 曲目管理（`TrackManager`）在手动 tab 保持可用。

### 设备歌单回归（不改行为，只标注来源）

- [x] 8. 设备歌单候选仍来自两个来源的全部已下载合集，未做收窄。
- [x] 9. `app/candidate-picker.tsx` + `backend/kids-catalog/src/main.py`：
      候选行标注合集来源（榜单 / 手动添加），并进一步标注平台（榜单=喜马拉雅 / 手动=网易云）。

## 规范沉淀

- [x] 10. `.trellis/spec/apps/kids-catalog/frontend/index.md`：Page Structure 段已补写
      三 tab 结构、`?tab=` 取值、专辑卡片复用规则、`useSearchParams` 需 Suspense 边界的构建约束。

## 验证命令

```bash
cd apps/kids-catalog && pnpm exec tsc --noEmit && pnpm build
cd backend/kids-catalog && .venv/Scripts/python -m pytest -q
```

- 手动验收：`/kids` 三个 tab 逐一核对 prd.md 验收标准；设备歌单候选含两来源已下载合集。

## 回滚点

- 前端单文件改动，`git revert 080a16fe` 即恢复合并列表视图；
  来源标注为独立提交（`9e835a72`、`bc1c174f`），可单独回滚。
- 后端仅候选列表增加来源字段输出，无 schema 迁移，无数据回滚需求。
