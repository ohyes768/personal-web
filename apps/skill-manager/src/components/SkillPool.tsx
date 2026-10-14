'use client';

import type { ReactNode } from 'react';
import type { QueueEntry, TargetKey } from '@/lib/queue';
import type { ExportTarget, SkillCard, TargetDeployment } from '@/lib/types';
import { shortRepo } from '@/lib/format';
import { collectionStats, groupCollections, type SkillCollection } from '@/lib/collections';
import { exportTargetLabel, LINK_TARGETS, TARGET_LABEL, type ExportTargetKey } from '@/lib/targets';
import {
  DownloadIcon,
  HermesIcon,
  PencilIcon,
  TrashIcon,
  UnlinkIcon,
} from '@/components/icons';

const ALL_TARGETS = LINK_TARGETS;

/** target 队列 chip 的品牌语义色：Hermes=神使蓝。 */
const TARGET_ICON: Record<TargetKey, { icon: ReactNode; hover: string }> = {
  hermes: { icon: <HermesIcon />, hover: 'hover:text-sky-600' },
};

interface SkillPoolProps {
  exportTargets: ExportTarget[];
  skills: SkillCard[];
  allSkills?: SkillCard[];
  onAddCollection?: (collection: SkillCollection, target: TargetKey) => void;
  onCheckCollection?: (collection: SkillCollection) => void;
  checkingUpdates?: boolean;
  queue: QueueEntry[];
  selectedIds?: string[];
  onSelect?: (id: string, selected: boolean) => void;
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

/** 左栏单张 Skill 卡片：target 点击即切换入队/出队；部署状态只读徽章。 */
function SkillCardItem({
  skill,
  exportTargets,
  queuedTargets,
  selected,
  onSelect,
  onToggleQueueTarget,
  onClone,
  onDelete,
  onUnpublish,
  onEditTags,
  onExport,
  onDeleteExport,
}: {
  skill: SkillCard;
  exportTargets: ExportTarget[];
  queuedTargets: TargetKey[];
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
  onToggleQueueTarget: SkillPoolProps['onToggleQueueTarget'];
  onClone: SkillPoolProps['onClone'];
  onDelete: SkillPoolProps['onDelete'];
  onUnpublish: SkillPoolProps['onUnpublish'];
  onEditTags: SkillPoolProps['onEditTags'];
  onExport: SkillPoolProps['onExport'];
  onDeleteExport: SkillPoolProps['onDeleteExport'];
}) {
  const cacheMissing = skill.cache_missing;
  const sourceMissing = skill.source_missing;
  const publishBlocked = cacheMissing || sourceMissing;
  const activeTargets = ALL_TARGETS.filter(
    (target) => skill.deployments[target]?.status === 'active'
  );
  // 副标题只在有额外信息时出现：id 与 name 重复就不显示；GitHub 显示缩短仓库
  const subtitle =
    skill.source === 'github' && skill.repository
      ? shortRepo(skill.repository)
      : skill.id !== skill.name
        ? skill.id
        : '';

  return (
    <li className="flex flex-col rounded-lg border border-slate-200 bg-white p-3">
      {skill.source === 'github' && onSelect && <label className="mb-2 text-xs text-slate-600"><input type="checkbox" checked={!!selected} disabled={publishBlocked} onChange={e => onSelect(e.target.checked)} /> 选择 {skill.name}</label>}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-medium text-slate-800">{skill.name}</h3>
          {subtitle ? (
            <p className="truncate text-xs text-slate-400" title={subtitle}>
              {subtitle}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span
            className={`rounded px-1.5 py-0.5 text-xs ${
              skill.source === 'local'
                ? 'bg-violet-50 text-violet-700'
                : 'bg-sky-50 text-sky-700'
            }`}
          >
            {skill.source === 'local' ? '自研' : 'GitHub'}
          </span>
          {skill.status === 'deprecated' ? (
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600">
              已弃用
            </span>
          ) : null}
          {skill.update?.has_update ? (
            <span
              className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800"
              title={`缓存 ${skill.update.cached_revision.slice(0, 7) || '无'} → 远端 ${skill.update.remote_revision.slice(0, 7)}`}
            >
              有更新 · {skill.update.remote_revision.slice(0, 7)}
            </span>
          ) : null}
        </div>
      </div>
      {skill.summary ? (
        <p className="mt-1.5 line-clamp-2 text-sm text-slate-600">{skill.summary}</p>
      ) : null}
      {skill.tags.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {skill.tags.map((tag) => (
            <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {tag}
            </span>
          ))}
          <button
            type="button"
            aria-label="编辑标签"
            data-tip="编辑标签"
            title="编辑该 Skill 的标签"
            onClick={() => onEditTags(skill)}
            className="icon-btn tip-right rounded-md border border-slate-300"
          >
            <PencilIcon />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onEditTags(skill)}
          className="mt-1.5 w-fit rounded-full bg-slate-50 px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-600"
        >
          + 添加标签
        </button>
      )}

      {/* Hermes 安装状态与外部导出记录 */}
      <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
        <InstallationBadge deployment={skill.deployments.hermes} />
        {Object.keys(skill.deployments).filter((target) => !LINK_TARGETS.includes(target as TargetKey)).map((target) => {
          const config = exportTargets.find((item) => item.id === target);
          const label = exportTargetLabel(exportTargets, target);
          const deployment = skill.deployments[target];
          if (!deployment || deployment.status !== 'active') return null;
          return <div key={target} className="flex items-center gap-1 text-xs">
            <button type="button" disabled={publishBlocked || !config?.enabled} onClick={() => onExport(skill, target)} title="点击重新导出" className={`min-w-0 flex-1 rounded px-1.5 py-1 text-left ${deployment.stale ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>
              {label}{!config?.enabled ? '（已停用）' : ''} · {(deployment.revision || deployment.content_hash)?.slice(0, 7) || '未知版本'} · {deployment.published_at.slice(5, 10)} · {deployment.stale ? '● 源已更新' : '最新'}
            </button>
            <button type="button" aria-label={`清除 ${label} 导出记录`} onClick={() => onDeleteExport(skill, target)} className="icon-btn rounded border border-slate-200"><TrashIcon /></button>
          </div>;
        })}
      </div>

      {/* 加入队列：target 图标 chip，点击即切换入队/出队（贴卡片底部） */}
      <div className="mt-auto flex items-center gap-2 border-t border-slate-100 pt-2">
        <button type="button" aria-label="导出 Skill" data-tip="导出 ZIP" title="选择目标并导出 ZIP" disabled={publishBlocked} onClick={() => onExport(skill)} className="icon-btn rounded-md border border-slate-300"><DownloadIcon /></button>
        {ALL_TARGETS.map((target) => {
          const queued = queuedTargets.includes(target);
          const { icon, hover } = TARGET_ICON[target];
          return (
            <button
              key={target}
              type="button"
              aria-label={`${TARGET_LABEL[target]} ${queued ? '安装到 Hermes' : '安装到 Hermes'}`}
              data-tip={
                publishBlocked
                  ? sourceMissing
                    ? '源缺失，无法安装'
                    : '请先 Clone 缓存'
                  : queued
                    ? `安装到 ${TARGET_LABEL[target]}`
                    : `安装到 ${TARGET_LABEL[target]}`
              }
              title={
                publishBlocked
                  ? sourceMissing
                    ? '源库登记目录缺失，无法安装'
                    : '请先 Clone 缓存'
                  : queued
                    ? `安装到 ${TARGET_LABEL[target]}`
                    : `安装到 ${TARGET_LABEL[target]}`
              }
              disabled={publishBlocked}
              onClick={() => onToggleQueueTarget(skill.id, target)}
              className={`icon-btn tip-left rounded-md border transition-colors ${
                queued
                  ? 'border-emerald-500 bg-emerald-500 text-white'
                  : `border-slate-300 bg-white ${hover}`
              }`}
            >
              {icon}<span className="ml-1 text-xs">{skill.deployments.hermes?.status === 'active' ? '更新' : '安装'}</span>
            </button>
          );
        })}
        {activeTargets.length > 0 ? (
          <button
            type="button"
            aria-label={`下架 ${TARGET_LABEL[activeTargets[0]]}${activeTargets.length > 1 ? ` 等 ${activeTargets.length} 个目标` : ''}`}
            data-tip={`下架（${activeTargets.map((t) => TARGET_LABEL[t]).join('、')}）`}
            title="已发布目标需先下架，下架后才会出现删除按钮"
            onClick={() => onUnpublish(skill.id, skill.name, activeTargets)}
            className="icon-btn tip-right icon-btn-danger rounded-md border border-rose-200"
          >
            <UnlinkIcon />
          </button>
        ) : (skill.source === 'github' || sourceMissing) ? (
          <button
            type="button"
            aria-label="删除"
            data-tip="删除登记与本机缓存"
            title="移除登记条目并删除本机缓存"
            onClick={() => onDelete(skill)}
            className="icon-btn tip-right icon-btn-danger rounded-md border border-slate-300"
          >
            <TrashIcon />
          </button>
        ) : null}
      </div>
      {cacheMissing ? (
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2">
          <span className="text-xs text-amber-700">
            缓存缺失：本环境没有该 Skill 的 GitHub 缓存，无法发布
          </span>
          <button
            type="button"
            aria-label="Clone 缓存"
            data-tip="Clone 缓存（安装前必做）"
            title="从 GitHub 拉取仓库到本机缓存，安装前必做"
            onClick={() => onClone(skill.id, skill.name)}
            className="icon-btn tip-right icon-btn-amber rounded-md bg-amber-600 text-white hover:text-white"
          >
            <DownloadIcon />
          </button>
        </div>
      ) : null}
      {sourceMissing ? (
        <p className="mt-2 border-t border-slate-100 pt-2 text-xs text-amber-700">
          源缺失：源库中该 Skill 目录不存在，无法发布；恢复目录后自动解除
        </p>
      ) : null}
    </li>
  );
}

export default function SkillPool({
  skills,
  allSkills = skills,
  onAddCollection,
  onCheckCollection,
  checkingUpdates,
  exportTargets,
  queue,
  selectedIds,
  onSelect,
  onToggleQueueTarget,
  onClone,
  onDelete,
  onUnpublish,
  onEditTags,
  onExport,
  onDeleteExport,
}: SkillPoolProps) {
  const queuedBySkill = new Map<string, TargetKey[]>();
  for (const entry of queue) {
    queuedBySkill.set(entry.skillId, entry.targets);
  }

  if (skills.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
        没有符合筛选条件的 Skill
      </p>
    );
  }

  function renderSkill(skill: SkillCard) {
    return (
        <SkillCardItem
          key={skill.id}
          skill={skill}
          selected={selectedIds?.includes(skill.id)}
          onSelect={onSelect ? selected => onSelect(skill.id, selected) : undefined}
          exportTargets={exportTargets}
          queuedTargets={queuedBySkill.get(skill.id) ?? []}
          onToggleQueueTarget={onToggleQueueTarget}
          onClone={onClone}
          onDelete={onDelete}
          onUnpublish={onUnpublish}
          onEditTags={onEditTags}
          onExport={onExport}
          onDeleteExport={onDeleteExport}
        />
    );
  }

  if (allSkills.some(skill => skill.source === 'github')) {
    return (
      <ul className="space-y-3">
        {groupCollections(allSkills, skills).map(collection => {
          const stats = collectionStats(collection.members);
          const missingCache = collection.members.find(s => s.cache_missing);
          return (
            <li key={collection.key} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-base font-semibold text-slate-800">{collection.name}</h3>
                  <p className="break-all text-xs text-slate-500">{collection.repository ?? '仓库地址异常，请展开检查'}</p>
                </div>
                <span className="rounded bg-sky-50 px-2 py-1 text-xs text-sky-700">GitHub 合集</span>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                已登记 {collection.members.length} 个 Skill
                {collection.visibleMembers.length !== collection.members.length ? ` · 匹配 ${collection.visibleMembers.length} 个` : ''}
              </p>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
                <span>已安装 {stats.published.hermes}/{collection.members.length}</span>
                {stats.abnormal > 0 ? <span className="text-amber-700">异常 {stats.abnormal} 项</span> : null}
                {stats.hasUpdate ? <span className="text-sky-700">有远端更新</span> : null}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {ALL_TARGETS.map(target => (
                  <button key={target} type="button" onClick={() => onAddCollection?.(collection, target)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50">
                    全部安装到 {TARGET_LABEL[target]}（{collection.members.length} 项）
                  </button>
                ))}
                <button type="button" disabled={checkingUpdates || !collection.repository}
                  onClick={() => onCheckCollection?.(collection)} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 disabled:opacity-50">
                  {checkingUpdates ? '检查中…' : '检查更新'}
                </button>
                {missingCache ? <button type="button" onClick={() => onClone(missingCache.id, collection.name)}
                  className="rounded border border-amber-300 px-2 py-1 text-xs text-amber-700">恢复仓库缓存</button> : null}
              </div>
              <details className="mt-3 border-t border-slate-100 pt-2">
                <summary className="cursor-pointer text-sm text-slate-600">成员详情（{collection.visibleMembers.length}）</summary>
                <ul className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">{collection.visibleMembers.map(renderSkill)}</ul>
              </details>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <ul className="grid grid-cols-1 items-stretch gap-2.5 md:grid-cols-2 lg:grid-cols-3">
      {skills.map(renderSkill)}
    </ul>
  );
}
