# Design — Skill Manager GitHub 合集 modal

## 1. 组件结构

新增 1 个组件 + 改 1 个组件 + 微调 1 个组件。

| 文件 | 操作 |
|---|---|
| `apps/skill-manager/src/components/CollectionDialog.tsx` | 新增（全屏 modal） |
| `apps/skill-manager/src/components/SkillPool.tsx` | 改：合集由 `<details>` 改为入口卡 + 渲染 `CollectionDialog` |
| `apps/skill-manager/src/components/SourceWorkspace.tsx` | 微调：回调 props 不变（仍传给 SkillPool），modal 用现有 onInstallSelection / onAddMembers / onCheckCollection / onDownloadCollection |

不引入 UI 库依赖（沿用 `ProfileScopePicker` 同款自写 modal，不引 Headless UI / Radix）。

## 2. CollectionDialog 接口

```tsx
'use client';

interface CollectionDialogProps {
  collection: SkillCollection;
  open: boolean;
  onClose: () => void;

  // 选择状态（modal 内部维护）
  // selectedIds 由 modal 内部 useState，不污染 SkillPool

  // 操作回调（与 SkillPool 现有 props 对齐）
  onInstallSelection: (skillIds: string[]) => void;
  onAddMembers: (repository: string) => void;
  onCheckCollection: (collection: SkillCollection) => void;
  onDownloadCollection: (collection: SkillCollection) => void;
  onExport: (skill: SkillCard, target?: ExportTargetKey) => void;
  onDeleteExport: (skill: SkillCard, target: ExportTargetKey) => void;
  onClone: (skillId: string, skillName: string) => void;
  onDelete: (skill: SkillCard) => void;
  onEditTags: (skill: SkillCard) => void;
  onUnpublish: (skillId: string, skillName: string, targets: TargetKey[]) => void;
  onToggleQueueTarget: (skillId: string, target: TargetKey) => void;

  // 数据依赖
  targets: InstallTarget[];
  exportTargets: ExportTarget[];
  queue: QueueEntry[];
  downloadingCollection: string | null;
  checkingUpdates: boolean;
}
```

modal 内部状态：
- `const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())`

## 3. modal 关闭逻辑（§R2、§R5）

```tsx
useEffect(() => {
  if (!open) return;
  function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose(); }
  document.addEventListener('keydown', onKey);
  return () => document.removeEventListener('keydown', onKey);
}, [open, onClose]);

// 背景点击关闭：modal 内容外包一层背景 div；onClick 触发 onClose，
// 内容 div 上 onClick stopPropagation 阻止冒泡。
```

路由变化时关闭：在 SkillPool 里 `useEffect(() => { setOpenCollection(null); }, [view])`（依赖父组件传入的 view prop）。CollectionDialog 自己不需要监听 URL。

## 4. 主 grid 入口卡（R1）

替换 `<details>` 为：

```tsx
<li
  key={collection.key}
  aria-label={`${collection.name} 合集`}
  className="flex min-w-0 flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
>
  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
    <span className="inline-flex items-center gap-1.5 rounded-md bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700">
      <CollectionIcon />{`合集 · ${collection.members.length} 项`}
    </span>
    <span className={`text-xs font-medium ${stats.published[current] === collection.members.length ? 'text-emerald-700' : 'text-slate-500'}`}>
      {stats.published[current] === collection.members.length
        ? `✓ ${collection.members.length}/${collection.members.length} 已全部安装`
        : `已安装 ${stats.published[current]}/${collection.members.length}`}
    </span>
  </div>
  <h3 className="truncate font-semibold text-slate-900" title={collection.name}>{collection.name}</h3>
  <p className="mt-0.5 truncate text-xs text-slate-400" title={collection.repository ?? '仓库地址异常'}>
    {collection.repository ?? '仓库地址异常，请联系管理员'}
  </p>
  <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-500">
    {collection.members.slice(0, 3).map(s => s.name).join('、')}
    {collection.members.length > 3 ? ` 等 ${collection.members.length} 个 Skill` : ''}
  </p>
  {/* 状态 chip 行（仅 N > 0 显示） */}
  <div className="mt-2 flex flex-wrap gap-2 text-xs">
    {exportCount > 0 ? (
      <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">
        📦 已导出 {exportCount} 目标
      </span>
    ) : null}
    {stats.hasUpdate ? (
      <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">🆕 有更新</span>
    ) : null}
    {stats.abnormal > 0 ? (
      <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">⚠ 异常 {stats.abnormal} 项</span>
    ) : null}
  </div>
  <div className="mt-auto flex items-center justify-end pt-4">
    <button
      type="button"
      onClick={() => setOpenCollection(collection)}
      className="inline-flex items-center gap-1 text-sm font-medium text-sky-700 hover:text-sky-800"
    >
      查看成员
      <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m6 3 5 5-5 5" /></svg>
    </button>
  </div>
</li>
```

新增 `exportCount` 计算（在 SkillPool 中）：扫描 `collection.members` 所有 `deployments`，累加非 install target 的 active export 数。

## 5. modal 布局（R3）

```tsx
{/* 背景遮罩 + 居中容器 */}
<div
  className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4"
  onClick={onClose} // 背景点击关闭
  role="dialog"
  aria-modal="true"
  aria-label={`${collection.name} 合集操作`}
>
  <div
    className="flex max-h-[85vh] w-full max-w-[960px] flex-col rounded-xl border border-slate-200 bg-white shadow-xl"
    onClick={e => e.stopPropagation()}
  >
    {/* header */}
    <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <div className="min-w-0">
        <div className="mb-1 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700">
            <CollectionIcon />合集 · {collection.members.length} 项
          </span>
          <span className={`text-xs font-medium ${complete ? 'text-emerald-700' : 'text-slate-500'}`}>
            {complete
              ? `✓ ${installed}/${collection.members.length} 已全部安装`
              : `已安装 ${installed}/${collection.members.length}${stats.abnormal > 0 ? ` · 异常 ${stats.abnormal}` : ''}`}
          </span>
        </div>
        <h2 className="truncate text-xl font-semibold text-slate-900">{collection.name}</h2>
        <p className="mt-0.5 truncate text-xs text-slate-400">{collection.repository ?? '仓库地址异常'}</p>
      </div>
      <button onClick={onClose} aria-label="关闭" className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
        <svg className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m3 3 10 10M13 3 3 13" /></svg>
      </button>
    </header>

    {/* toolbar */}
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/50 px-5 py-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button
          type="button"
          onClick={() => setSelectedIds(new Set(collection.members.map(s => s.id)))}
          className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50"
        >
          全选
        </button>
        <button
          type="button"
          disabled={!selectedIds.size}
          onClick={() => setSelectedIds(new Set())}
          className="rounded-md px-2 py-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
        >
          清空选择
        </button>
        <span className="text-slate-500">已选 {selectedIds.size} 项</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={!selectedIds.size || !onInstallSelection}
          onClick={() => { onInstallSelection?.([...selectedIds]); onClose(); }}
          className="rounded-md bg-sky-600 px-3 py-1.5 font-medium text-white hover:bg-sky-700 disabled:opacity-40"
        >
          安装所选 ({selectedIds.size})
        </button>
        <button
          type="button"
          disabled={installed === 0 || !onInstallSelection}
          onClick={() => { onInstallSelection(collection.members.map(s => s.id)); onClose(); }}
          className="rounded-md border border-sky-300 bg-white px-2.5 py-1.5 text-sky-700 hover:bg-sky-50 disabled:opacity-40"
          title="更新合集内所有已安装成员"
        >
          更新整个
        </button>
        <button
          type="button"
          disabled={installed === 0}
          onClick={() => { /* 弹确认 → 批量下架 */ }}
          className="rounded-md border border-rose-300 bg-white px-2.5 py-1.5 text-rose-700 hover:bg-rose-50 disabled:opacity-40"
        >
          下架整个
        </button>
        <button type="button" disabled={!!missingCache || !!downloadingCollection} onClick={() => onDownloadCollection(collection)} className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
          {downloadingCollection === collection.key ? '打包中…' : '下载合集'}
        </button>
        <button type="button" onClick={() => onAddMembers(`https://github.com/${collection.repository}`)} className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50">＋ 添加成员</button>
        <button type="button" disabled={!!checkingUpdates || !collection.repository} onClick={() => onCheckCollection(collection)} className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
          {checkingUpdates ? '检查中…' : '检查更新'}
        </button>
      </div>
    </div>

    {/* 状态 chip 摘要行（仅 N>0） */}
    {(exportCount > 0 || stats.hasUpdate || stats.abnormal > 0) ? (
      <div className="flex flex-wrap gap-2 border-b border-slate-100 bg-white px-5 py-2 text-xs">
        {exportCount > 0 ? <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">📦 已导出 {exportCount} 目标</span> : null}
        {stats.hasUpdate ? <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">🆕 有更新</span> : null}
        {stats.abnormal > 0 ? <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">⚠ 异常 {stats.abnormal} 项</span> : null}
      </div>
    ) : null}

    {/* body: 单列 row list */}
    <ul className="flex-1 overflow-y-auto divide-y divide-slate-100">
      {collection.members.map(skill => {
        const queued = queuedBySkill.get(skill.id) ?? [];
        const memberInstalled = skill.deployments[current]?.status === 'active' && !skill.deployments[current].link_missing;
        return (
          <li key={skill.id} className="flex items-start gap-3 px-5 py-3 hover:bg-slate-50/60">
            <input
              type="checkbox"
              aria-label={`选择 ${skill.name}`}
              checked={selectedIds.has(skill.id)}
              disabled={skill.cache_missing || skill.source_missing}
              onChange={e => setSelectedIds(prev => {
                const next = new Set(prev);
                if (e.target.checked) next.add(skill.id); else next.delete(skill.id);
                return next;
              })}
              className="mt-1 h-4 w-4 shrink-0 accent-sky-600"
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h3 className="truncate font-medium text-slate-800" title={skill.name}>{skill.name}</h3>
                <InstallationBadge deployment={skill.deployments[current]} />
                {skill.update?.has_update ? <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">有更新</span> : null}
              </div>
              {skill.summary ? <p className="mt-1 line-clamp-2 text-sm text-slate-600">{skill.summary}</p> : null}
              {skill.cache_missing ? <p className="mt-1 text-xs text-amber-700">缓存缺失，无法发布</p> : null}
              {skill.source_missing ? <p className="mt-1 text-xs text-amber-700">源缺失，无法发布</p> : null}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {skill.cache_missing ? (
                <button type="button" onClick={() => onClone(skill.id, skill.name)} className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100">
                  恢复缓存
                </button>
              ) : null}
              <button
                type="button"
                disabled={skill.cache_missing || skill.source_missing}
                onClick={() => { onToggleQueueTarget(skill.id, current); onClose(); }}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
                  memberInstalled
                    ? 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                    : queued.length
                    ? 'border-emerald-500 bg-emerald-500 text-white'
                    : 'border-sky-600 bg-sky-600 text-white hover:bg-sky-700'
                } disabled:opacity-40`}
              >
                {memberInstalled ? '更新' : '安装'}
              </button>
              {memberInstalled ? (
                <button
                  type="button"
                  onClick={() => {
                    const targets = Object.entries(skill.deployments).filter(([,d]) => d.status === 'active').map(([t]) => t as TargetKey);
                    onUnpublish(skill.id, skill.name, targets);
                    onClose();
                  }}
                  className="rounded-md border border-rose-200 bg-white px-2.5 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50"
                >
                  下架
                </button>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  </div>
</div>
```

## 6. 边界 / 错误处理

| 场景 | 行为 |
|---|---|
| `collection.members.length === 0` | modal 显示「暂无成员」空态；toolbar 主按钮 disabled |
| 全选后所有成员都被禁用（cache_missing） | 「安装所选」disabled + 提示 tooltip |
| 单成员安装后 modal 关闭 | 父组件 `setNotice` 显示「已加入 N 项到安装计划」 |
| 单成员下架（直接调 onUnpublish） | modal 关闭，父组件 ConfirmActionDialog 弹出确认 |
| 批量下架（点「下架整个」时 installed > 0） | 弹 ConfirmActionDialog 一次性确认 |
| 用户切 view（URL 变） | modal 通过 SkillPool 的 `useEffect(() => setOpenCollection(null), [view])` 关闭 |
| modal 打开时主 grid 滚动位置 | 不重置；用户关闭 modal 后看到原滚动位置 |

## 7. Tradeoff

| 决策 | 替代 | 选这个的理由 |
|---|---|---|
| 自写 modal（无 Headless UI） | Headless UI Dialog / Radix | 跟 ProfileScopePicker 风格一致；零依赖；现有 dialog（ConfirmActionDialog 等）都是自写 |
| row list（modal 内成员用 list） | grid（modal 内成员用 card grid） | 12-14 个成员 row list 视觉密度更可扫；"合集 = 一组相关项"用 row 表达更准 |
| modal 关闭时焦点回触发卡 | 焦点丢失 | 可访问性基本要求；用 `ref` + `useEffect` onClose 时 `.focus()` |
| 单成员操作（安装/下架）后立即关 modal | 保留 modal 显示 progress | 一期 modal 不展示 progress，父 notice 提示；二期可加 in-modal progress |
| 「更新整个」「下架整个」次级主按钮（outline） | 同「安装所选」一样 filled | 三类操作视觉权重分清：主 = filled sky，次级主 = outline，次级 = outline slate |
| modal 内不暴露 删除/编辑标签/导出 | 行内 hover 菜单 | 删除/标签/导出属于"对成员的独立管理"，modal 是批量场景；让用户回到主 grid 入口卡视角更合适 |
| 单成员合集（1 个 member）走独立卡 | 任何合集都走 modal | 单成员没必要 modal；维持现状 `renderSkill` 路径 |
| 状态 chip 行仅 N>0 显示 | 全部 3 个 chip 总显示 | 0 项时显示空 chip 是噪声；按需显形降低视觉密度 |

## 8. 兼容性 / 回归风险

- ✅ `SkillCollection` 数据结构不动 → `groupCollections` / `collectionStats` 复用
- ✅ `SkillPool` 现有 props 大部分保留 → `SourceWorkspace` 几乎不动
- ⚠️ 删除 `<details>` 折叠展开语义 → 已迁移到 modal（行为更清晰）
- ⚠️ 删除成员卡 inline export/delete/edit-tags 入口 → 一期不暴露（spec §R4）；用户回主 grid 找；二期可加 modal 内 hover 菜单
- ⚠️ SkillPool.test.ts 中关于 `<details>` 行为的断言（如有）需更新

## 9. 实施顺序（与 implement.md 对齐）

1. 新增 `CollectionDialog.tsx` + test
2. 改 `SkillPool.tsx`：删 `<details>`，改为入口卡 + 渲染 CollectionDialog
3. 计算 `exportCount`（在 SkillPool 中）
4. 跑 lint/typecheck/build
5. Live browser 验收截图

## 10. 回滚形状

- 新增 1 个组件 + 改 1 个文件
- 改回旧版：删 CollectionDialog + 把 SkillPool 入口卡部分 revert 到 `<details>` 结构（git revert）
- 不涉及数据迁移、后端 API、数据库 schema
- 实施中途发现重大问题：保留 CollectionDialog 但不挂载到 SkillPool（零风险回滚到现状）
