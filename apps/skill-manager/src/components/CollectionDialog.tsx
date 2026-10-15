'use client';

import { useEffect, useState } from 'react';
import { useInstallTargets, installTargetLabel, type InstallTarget } from '@/lib/installTargets';
import { collectionStats, type SkillCollection } from '@/lib/collections';
import { isInstallTarget, type ExportTargetKey } from '@/lib/targets';
import type { QueueEntry, TargetKey } from '@/lib/queue';
import type { SkillCard, TargetDeployment } from '@/lib/types';
import { CollectionIcon } from '@/components/icons';

interface CollectionDialogProps {
  collection: SkillCollection;
  open: boolean;
  onClose: () => void;
  onInstallSelection?: (skillIds: string[]) => void;
  onAddMembers?: (repository: string) => void;
  onCheckCollection?: (collection: SkillCollection) => void;
  onDownloadCollection?: (collection: SkillCollection) => void;
  downloadingCollection?: string | null;
  checkingUpdates?: boolean;
  targets: InstallTarget[];
  queue: QueueEntry[];
  onToggleQueueTarget: (skillId: string, target: TargetKey) => void;
  onClone: (skillId: string, skillName: string) => void;
  onDelete: (skill: SkillCard) => void;
  onUnpublish: (skillId: string, skillName: string, targets: TargetKey[]) => void;
  onEditTags: (skill: SkillCard) => void;
  onExport: (skill: SkillCard, target?: ExportTargetKey) => void;
  onDeleteExport: (skill: SkillCard, target: ExportTargetKey) => void;
}

function InstallationBadge({ deployment }: { deployment?: TargetDeployment }) {
  const badgeClass = 'inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 text-xs font-medium leading-none';
  if (!deployment || deployment.status === 'removed') {
    return (
      <span className={`${badgeClass} border-slate-200 bg-slate-50 text-slate-600`}>
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-slate-400" />
        未安装
      </span>
    );
  }
  if (deployment.status === 'active' && deployment.link_missing) {
    return (
      <span
        className={`${badgeClass} border-amber-200 bg-amber-50 text-amber-800`}
        title="安装记录仍在，但 Hermes 目录中的链接已不存在，可重新安装恢复"
      >
        <span aria-hidden="true" className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-amber-600 text-[10px] font-bold text-white">!</span>
        未安装 · 链接缺失
      </span>
    );
  }
  if (deployment.status === 'active') {
    return (
      <span className={`${badgeClass} border-emerald-200 bg-emerald-50 text-emerald-800`}
        title={deployment.revision ? `安装版本：${deployment.revision}` : undefined}>
        <svg aria-hidden="true" className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3.5 8 3 3 6-6" /></svg>
        已安装
      </span>
    );
  }
  return (
    <span className={`${badgeClass} border-amber-200 bg-amber-50 text-amber-800`}>
      {deployment.status}
    </span>
  );
}

/**
 * GitHub 合集的全屏 modal（PRD §R2-R4）。
 *
 * 单列 row list 展示成员；toolbar 提供 全选 / 清空 / 安装所选 / 更新整个 / 下架整个 /
 * 下载合集 / 添加成员 / 检查更新。
 *
 * 关闭：右上 X / Esc 键 / 背景点击（点击内容不关）。
 */
export default function CollectionDialog({
  collection,
  open,
  onClose,
  onInstallSelection,
  onAddMembers,
  onCheckCollection,
  onDownloadCollection,
  downloadingCollection,
  checkingUpdates,
  targets,
  queue,
  onToggleQueueTarget,
  onClone,
  onUnpublish,
}: CollectionDialogProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmBatchUnpublish, setConfirmBatchUnpublish] = useState(false);
  const { current } = useInstallTargets();

  // Esc 键关闭
  useEffect(() => {
    if (!open || typeof document === 'undefined') return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose();
      }
    }
    document.addEventListener('keydown', onKey);
    return () => {
      if (typeof document !== 'undefined') document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  // 打开时重置选择状态
  useEffect(() => {
    if (open) {
      setSelectedIds(new Set());
    }
  }, [open]);

  if (!open) return null;

  const stats = collectionStats(collection.members, current);
  const installed = stats.published[current];
  const total = collection.members.length;
  const complete = installed === total;
  const missingCache = collection.members.find(m => m.cache_missing);
  const label = (id: string) => installTargetLabel(targets, id);
  const exportCount = collection.members.reduce((sum, m) => {
    return sum + Object.entries(m.deployments).filter(
      ([target, deployment]) => !isInstallTarget(target) && deployment.status === 'active'
    ).length;
  }, 0);
  const queuedBySkill = new Map<string, TargetKey[]>();
  for (const entry of queue) {
    queuedBySkill.set(entry.skillId, entry.targets);
  }

  function handleSelectAll() {
    const selectable = collection.members
      .filter(s => !s.cache_missing && !s.source_missing)
      .map(s => s.id);
    setSelectedIds(new Set(selectable));
  }
  function handleClearSelection() {
    setSelectedIds(new Set());
  }
  function handleToggleSelected(skillId: string, checked: boolean) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (checked) next.add(skillId); else next.delete(skillId);
      return next;
    });
  }
  function handleInstallSelection() {
    const ids = [...selectedIds];
    if (!ids.length) return;
    onInstallSelection?.(ids);
    onClose();
  }
  function handleUpdateAll() {
    if (installed === 0) return;
    onInstallSelection?.(collection.members.map(s => s.id));
    onClose();
  }
  function handleUnpublishAll() {
    setConfirmBatchUnpublish(true);
  }
  function confirmUnpublishAll() {
    const targets: TargetKey[] = [current];
    for (const skill of collection.members) {
      if (Object.values(skill.deployments).some(d => d.status === 'active')) {
        onUnpublish(skill.id, skill.name, targets);
      }
    }
    setConfirmBatchUnpublish(false);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${collection.name} 合集操作`}
    >
      <div
        className="relative flex max-h-[85vh] w-full max-w-[960px] flex-col rounded-xl border border-slate-200 bg-white shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        {/* header */}
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-md bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700">
                <CollectionIcon />合集 · {total} 项
              </span>
              <span className={`text-xs font-medium ${complete ? 'text-emerald-700' : 'text-slate-500'}`}>
                {complete
                  ? `✓ ${installed}/${total} 已全部安装`
                  : `已安装 ${installed}/${total}${stats.abnormal > 0 ? ` · 异常 ${stats.abnormal}` : ''}`}
              </span>
            </div>
            <h2 className="truncate text-xl font-semibold text-slate-900" title={collection.name}>{collection.name}</h2>
            <p className="mt-0.5 truncate text-xs text-slate-400" title={collection.repository ?? '仓库地址异常'}>
              {collection.repository ?? '仓库地址异常，请联系管理员'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            data-dialog-close="true"
            className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <svg aria-hidden="true" className="h-5 w-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 3 10 10M13 3 3 13" /></svg>
          </button>
        </header>

        {/* toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/50 px-5 py-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button
              type="button"
              onClick={handleSelectAll}
              disabled={!collection.members.some(s => !s.cache_missing && !s.source_missing)}
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              全选
            </button>
            <button
              type="button"
              disabled={!selectedIds.size}
              onClick={handleClearSelection}
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
              onClick={handleInstallSelection}
              data-action="install-selected"
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-40"
            >
              安装所选 ({selectedIds.size})
            </button>
            <button
              type="button"
              disabled={installed === 0 || !onInstallSelection}
              onClick={handleUpdateAll}
              title="更新合集内所有已安装成员"
              className="rounded-md border border-sky-300 bg-white px-2.5 py-1.5 text-sm text-sky-700 hover:bg-sky-50 disabled:opacity-40"
            >
              更新整个
            </button>
            <button
              type="button"
              disabled={installed === 0}
              onClick={handleUnpublishAll}
              title="下架合集内所有已安装成员"
              className="rounded-md border border-rose-300 bg-white px-2.5 py-1.5 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-40"
            >
              下架整个
            </button>
            {onDownloadCollection ? <button
              type="button"
              disabled={!!missingCache || !collection.repository || !!downloadingCollection}
              onClick={() => onDownloadCollection(collection)}
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              {downloadingCollection === collection.key ? '打包中…' : '下载合集'}
            </button> : null}
            {onAddMembers && collection.repository ? <button
              type="button"
              onClick={() => onAddMembers(`https://github.com/${collection.repository}`)}
              title="重新扫描此仓库，补充未登记的 Skill"
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              ＋ 添加成员
            </button> : null}
            <button
              type="button"
              disabled={!!checkingUpdates || !collection.repository}
              onClick={() => onCheckCollection?.(collection)}
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              {checkingUpdates ? '检查中…' : '检查更新'}
            </button>
          </div>
        </div>

        {/* 状态 chip 摘要行（仅 N>0） */}
        {(exportCount > 0 || stats.hasUpdate || stats.abnormal > 0) ? (
          <div className="flex flex-wrap gap-2 border-b border-slate-100 bg-white px-5 py-2 text-xs">
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
        ) : null}

        {/* body: 单列 row list */}
        {collection.members.length === 0 ? (
          <div className="flex-1 overflow-y-auto px-5 py-12 text-center text-sm text-slate-400">
            暂无成员
          </div>
        ) : (
          <ul className="flex-1 overflow-y-auto divide-y divide-slate-100">
            {collection.members.map(skill => {
              const queued = queuedBySkill.get(skill.id) ?? [];
              const memberInstalled = skill.deployments[current]?.status === 'active' && !skill.deployments[current].link_missing;
              const activeTargets = Object.entries(skill.deployments)
                .filter(([target, deployment]) => isInstallTarget(target) && deployment.status === 'active')
                .map(([target]) => target as TargetKey);
              const sourceBlocked = skill.cache_missing || skill.source_missing;
              return (
                <li key={skill.id} className="flex items-start gap-3 px-5 py-3 hover:bg-slate-50/60">
                  <input
                    type="checkbox"
                    aria-label={`选择 ${skill.name}`}
                    checked={selectedIds.has(skill.id)}
                    disabled={sourceBlocked}
                    onChange={e => handleToggleSelected(skill.id, e.target.checked)}
                    className="mt-1 h-4 w-4 shrink-0 accent-sky-600"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <h3 className="truncate font-medium text-slate-800" title={skill.name}>{skill.name}</h3>
                      <InstallationBadge deployment={skill.deployments[current]} />
                      {skill.update?.has_update ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span
                            className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800"
                            title={`缓存 ${skill.update.cached_revision.slice(0, 7) || '无'} → 远端 ${skill.update.remote_revision.slice(0, 7)}`}
                          >
                            有更新
                          </span>
                          <button
                            type="button"
                            onClick={() => onClone(skill.id, skill.name)}
                            className="rounded-md border border-amber-300 bg-white px-2 py-0.5 text-xs text-amber-700 hover:bg-amber-50"
                            title="从 GitHub 拉取最新版本到本机缓存"
                          >
                            同步缓存
                          </button>
                        </span>
                      ) : null}
                    </div>
                    {skill.summary ? <p className="mt-1 line-clamp-2 text-sm text-slate-600">{skill.summary}</p> : null}
                    {skill.cache_missing ? (
                      <p className="mt-1 text-xs text-amber-700">缓存缺失，无法发布</p>
                    ) : null}
                    {skill.source_missing ? (
                      <p className="mt-1 text-xs text-amber-700">源缺失，无法发布</p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    {skill.cache_missing ? (
                      <button
                        type="button"
                        onClick={() => onClone(skill.id, skill.name)}
                        className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100"
                      >
                        恢复缓存
                      </button>
                    ) : null}
                    <button
                      type="button"
                      aria-label={`${memberInstalled ? '更新' : '安装'} ${skill.name}`}
                      disabled={sourceBlocked}
                      onClick={() => { onToggleQueueTarget(skill.id, current); onClose(); }}
                      className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                        memberInstalled
                          ? 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                          : queued.length
                          ? 'border-emerald-500 bg-emerald-500 text-white'
                          : 'border-sky-600 bg-sky-600 text-white hover:border-sky-700 hover:bg-sky-700'
                      }`}
                    >
                      {memberInstalled ? '更新' : '安装'}
                    </button>
                    {activeTargets.length > 0 ? (
                      <button
                        type="button"
                        aria-label={`下架 ${skill.name}`}
                        onClick={() => { onUnpublish(skill.id, skill.name, activeTargets); onClose(); }}
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
        )}

        {/* 批量下架确认（覆盖在内容区上方） */}
        {confirmBatchUnpublish ? (
          <div
            className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-slate-900/40"
            role="dialog"
            aria-modal="true"
            aria-label="确认批量下架"
            onClick={() => setConfirmBatchUnpublish(false)}
          >
            <div
              className="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl"
              onClick={e => e.stopPropagation()}
            >
              <h3 className="text-lg font-semibold text-slate-800">确认批量下架</h3>
              <p className="mt-2 text-sm text-slate-600">
                将下架「{collection.name}」中 {installed} 个已安装成员（目标 {label(current)}）。下架后可在主 grid 重新安装。
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmBatchUnpublish(false)}
                  className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={confirmUnpublishAll}
                  className="rounded bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700"
                >
                  确认下架
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}