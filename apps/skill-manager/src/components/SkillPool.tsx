'use client';

import { useInstallTargets, installTargetLabel } from '@/lib/installTargets';
import type { QueueEntry, TargetKey } from '@/lib/queue';
import type { ExportTarget, SkillCard, TargetDeployment } from '@/lib/types';
import { collectionStats, groupCollections, repositoryKey, type SkillCollection } from '@/lib/collections';
import { exportTargetLabel, isInstallTarget, type ExportTargetKey } from '@/lib/targets';
import {
  DownloadIcon,
  PencilIcon,
  TrashIcon,
  CollectionIcon,
  SkillDocumentIcon,
} from '@/components/icons';


const SKILL_GRID_CLASS = 'grid grid-cols-1 items-stretch gap-3 md:grid-cols-2 lg:grid-cols-3';

interface SkillPoolProps {
  exportTargets: ExportTarget[];
  skills: SkillCard[];
  allSkills?: SkillCard[];
  onInstallSelection?: (skillIds: string[]) => void;
  onAddMembers?: (repository: string) => void;
  onCheckCollection?: (collection: SkillCollection) => void;
  onDownloadCollection?: (collection: SkillCollection) => void;
  downloadingCollection?: string | null;
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
  inCollection = false,
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
  inCollection?: boolean;
  onToggleQueueTarget: SkillPoolProps['onToggleQueueTarget'];
  onClone: SkillPoolProps['onClone'];
  onDelete: SkillPoolProps['onDelete'];
  onUnpublish: SkillPoolProps['onUnpublish'];
  onEditTags: SkillPoolProps['onEditTags'];
  onExport: SkillPoolProps['onExport'];
  onDeleteExport: SkillPoolProps['onDeleteExport'];
}) {
  const {current, targets, loading, error} = useInstallTargets();
  const ALL_TARGETS = [current];
  const label = (id: string) => installTargetLabel(targets, id);
  const unavailable = loading || !!error || (targets.length > 0 && !targets.find(t => t.id === current)?.available);
  const cacheMissing = skill.cache_missing;
  const sourceMissing = skill.source_missing;
  const sourceBlocked = cacheMissing || sourceMissing;
  const publishBlocked = sourceBlocked || unavailable;
  const targetReason = loading ? '安装目标加载中…' : error || targets.find(t => t.id === current)?.unavailable_reason || '当前 profile 不可用';
  const installed = skill.deployments[current]?.status === 'active' && !skill.deployments[current].link_missing;
  const hasPendingUpdate = !!skill.update?.has_update || !!skill.deployments[current]?.stale;
  const exportEntries = Object.entries(skill.deployments).filter(
    ([target, deployment]) => !isInstallTarget(target) && deployment.status === 'active'
  );
  const activeTargets = ALL_TARGETS.filter(
    (target) => skill.deployments[target]?.status === 'active'
  );
  // 合集成员共用头部仓库身份；独立 GitHub 卡片自行展示仓库。
  const subtitle = skill.source === 'github'
    ? inCollection ? '' : repositoryKey(skill.repository) ?? skill.repository ?? '仓库地址缺失'
    : skill.id !== skill.name ? skill.id : '';

  return (
    <li className={`flex min-w-0 flex-col rounded-xl border border-slate-200 bg-white ${skill.source === 'github' && !inCollection ? 'min-h-56 p-4 shadow-sm' : 'p-3'}`}>
      {skill.source === 'github' && !inCollection ? (
        <div className="mb-3">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
            <SkillDocumentIcon />独立 Skill
          </span>
        </div>
      ) : null}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {inCollection && onSelect ? (
              <input type="checkbox" aria-label={`选择 ${skill.name}`} checked={!!selected}
                disabled={publishBlocked} onChange={e => onSelect(e.target.checked)}
                className="h-4 w-4 shrink-0 accent-sky-600" />
            ) : null}
            <h3 className="min-w-0 truncate font-medium text-slate-800" title={skill.name}>{skill.name}</h3>
            <InstallationBadge deployment={skill.deployments[current]} />
          </div>
          {subtitle ? (
            <p className="truncate text-xs text-slate-400" title={subtitle}>
              {subtitle}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {skill.source === 'local' ? <span className="rounded bg-violet-50 px-1.5 py-0.5 text-xs text-violet-700">自研</span> : null}
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

      {/* 有外部导出记录时才占用额外一行 */}
      {exportEntries.length > 0 ? <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
        {exportEntries.map(([target, deployment]) => {
          const config = exportTargets.find((item) => item.id === target);
          const label = exportTargetLabel(exportTargets, target);
          return <div key={target} className="flex items-center gap-1 text-xs">
            <button type="button" disabled={sourceBlocked || !config?.enabled} onClick={() => onExport(skill, target)} title="点击重新导出" className={`min-w-0 flex-1 rounded px-1.5 py-1 text-left ${deployment.stale ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>
              {label}{!config?.enabled ? '（已停用）' : ''} · {(deployment.revision || deployment.content_hash)?.slice(0, 7) || '未知版本'} · {deployment.published_at.slice(5, 10)} · {deployment.stale ? '● 源已更新' : '最新'}
            </button>
            <button type="button" aria-label={`清除 ${label} 导出记录`} onClick={() => onDeleteExport(skill, target)} className="icon-btn rounded border border-slate-200"><TrashIcon /></button>
          </div>;
        })}
      </div> : null}

      {/* 安装为文字主按钮，其余操作保留图标 */}
      <div className="mt-auto flex items-center gap-2 border-t border-slate-100 pt-3">
        <button type="button" aria-label="导出 Skill" data-tip="导出 ZIP" title="选择目标并导出 ZIP" disabled={sourceBlocked} onClick={() => onExport(skill)} className="icon-btn tip-left rounded-md border border-slate-300"><DownloadIcon /></button>
        {!(skill.source === 'local' && installed) && ALL_TARGETS.map((target) => {
          const queued = queuedTargets.includes(target);
          return (
            <button
              key={target}
              type="button"
              aria-label={`${installed ? '更新' : '安装'} ${skill.name}`}
              data-tip={
                publishBlocked
                  ? unavailable ? targetReason : sourceMissing
                    ? '源缺失，无法安装'
                    : '请先 Clone 缓存'
                  : queued
                    ? `安装到 ${label(target)}`
                    : `安装到 ${label(target)}`
              }
              title={
                publishBlocked
                  ? unavailable ? targetReason : sourceMissing
                    ? '源库登记目录缺失，无法安装'
                    : '请先 Clone 缓存'
                  : queued
                    ? `安装到 ${label(target)}`
                    : `安装到 ${label(target)}`
              }
              disabled={publishBlocked}
              onClick={() => onToggleQueueTarget(skill.id, target)}
              className={`tip-right ml-auto inline-flex h-8 items-center justify-center rounded-md border px-3 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 disabled:cursor-not-allowed disabled:opacity-40 ${
                installed && !hasPendingUpdate
                  ? 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                  : queued
                  ? 'border-emerald-500 bg-emerald-500 text-white'
                  : 'border-sky-600 bg-sky-600 text-white hover:border-sky-700 hover:bg-sky-700'
              }`}
            >
              {installed ? '更新' : '安装'}
            </button>
          );
        })}
        {activeTargets.length > 0 ? (
          <button
            type="button"
            aria-label={`下架 ${label(activeTargets[0])}${activeTargets.length > 1 ? ` 等 ${activeTargets.length} 个目标` : ''}`}
            data-tip={`下架（${activeTargets.map((t) => label(t)).join('、')}）`}
            title="已发布目标需先下架，下架后才会出现删除按钮"
            onClick={() => onUnpublish(skill.id, skill.name, activeTargets)}
            className="tip-right inline-flex h-8 items-center justify-center rounded-md border border-rose-200 bg-white px-3 text-xs font-medium text-rose-600 transition-colors hover:border-rose-300 hover:bg-rose-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-500"
          >
            下架
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
  onInstallSelection,
  onAddMembers,
  onCheckCollection,
  onDownloadCollection,
  downloadingCollection,
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
  const {current} = useInstallTargets();
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

  function renderSkill(skill: SkillCard, inCollection = false) {
    return (
        <SkillCardItem
          key={skill.id}
          skill={skill}
          inCollection={inCollection}
          selected={selectedIds?.includes(skill.id)}
          onSelect={inCollection && onSelect ? selected => onSelect(skill.id, selected) : undefined}
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
      <ul className={SKILL_GRID_CLASS}>
        {groupCollections(allSkills, skills).map(collection => {
          // 按完整登记成员数判断，筛选为单个结果时仍保留原合集。
          if (collection.members.length === 1) return renderSkill(collection.visibleMembers[0]);
          const stats = collectionStats(collection.members, current);
          const missingCache = collection.members.find(s => s.cache_missing);
          const selectable = collection.visibleMembers.filter(s => !s.cache_missing && !s.source_missing);
          const selectedMembers = collection.members.filter(s => selectedIds?.includes(s.id) && !s.cache_missing && !s.source_missing);
          const visibleIds = new Set(collection.visibleMembers.map(s => s.id));
          const hiddenSelected = selectedMembers.filter(s => !visibleIds.has(s.id)).length;
          return (
            <li key={collection.key} aria-label={`${collection.name} 合集`}
              className="min-w-0 rounded-xl border border-slate-200 bg-white shadow-sm transition-colors has-[details[open]]:col-span-full has-[details[open]]:border-sky-200">
              <details className="group h-full open:h-auto">
                <summary className="collection-summary flex h-full min-h-56 cursor-pointer list-none flex-col p-4 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-500 group-open:h-auto group-open:min-h-0">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700">
                      <CollectionIcon />{`合集 · ${collection.members.length} 项`}
                    </span>
                    <span className={`text-xs font-medium ${stats.published[current] === collection.members.length ? 'text-emerald-700' : 'text-slate-500'}`}>
                      已安装 {stats.published[current]}/{collection.members.length}
                    </span>
                  </div>
                  <h3 className="truncate font-semibold text-slate-900" title={collection.name}>{collection.name}</h3>
                  <p className="mt-0.5 truncate text-xs text-slate-400" title={collection.repository ?? '仓库地址异常'}>
                    {collection.repository ?? '仓库地址异常，请展开检查'}
                  </p>
                  <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-500 group-open:hidden">
                    {collection.members.slice(0, 3).map(s => s.name).join('、')}
                    {collection.members.length > 3 ? ` 等 ${collection.members.length} 个 Skill` : ''}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    {collection.visibleMembers.length !== collection.members.length ? <span className="text-slate-500">匹配 {collection.visibleMembers.length} 个</span> : null}
                    {stats.abnormal > 0 ? <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">异常 {stats.abnormal} 项</span> : null}
                    {stats.hasUpdate ? <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">有远端更新</span> : null}
                  </div>
                  <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-xs group-open:mt-0 group-open:pt-3">
                    <span className="text-slate-400">已登记 {collection.members.length} 个 Skill</span>
                    <span className="inline-flex items-center gap-1 font-medium text-sky-700">
                      <span className="group-open:hidden">查看成员</span>
                      <span className="hidden group-open:inline">收起成员</span>
                      <svg aria-hidden="true" className="h-3.5 w-3.5 transition-transform group-open:rotate-90 motion-reduce:transition-none" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m6 3 5 5-5 5" /></svg>
                    </span>
                  </div>
                </summary>
                <div className="border-t border-slate-100 bg-slate-50/70 p-3 sm:p-4">
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                    {onSelect ? <>
                      <button type="button" disabled={!selectable.length}
                        onClick={() => selectable.forEach(s => onSelect(s.id, true))}
                        className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-40">
                        {collection.visibleMembers.length === collection.members.length ? '全选' : '全选匹配项'}
                      </button>
                      <button type="button" disabled={!selectedMembers.length}
                        onClick={() => collection.members.forEach(s => onSelect(s.id, false))}
                        className="rounded-md px-2 py-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-40">清空选择</button>
                      <span className="text-slate-500">已选 {selectedMembers.length} 项{hiddenSelected ? `（含 ${hiddenSelected} 个隐藏项）` : ''}</span>
                    </> : null}
                    <div className="ml-auto flex flex-wrap items-center gap-2">
                      {onDownloadCollection ? <button type="button"
                        disabled={!!missingCache || !collection.repository || !!downloadingCollection}
                        onClick={() => onDownloadCollection(collection)}
                        title="下载完整仓库，保留入口说明、路由、全部成员和公共文件；不受筛选或勾选影响"
                        className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
                        {downloadingCollection === collection.key ? '打包中…' : '下载合集'}
                      </button> : null}
                      {onAddMembers && collection.repository ? <button type="button"
                        aria-label={`为 ${collection.repository} 添加成员`}
                        onClick={() => onAddMembers(`https://github.com/${collection.repository}`)}
                        title="重新扫描此仓库，补充未登记的 Skill"
                        className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50">
                        ＋ 添加成员
                      </button> : null}
                      <button type="button" disabled={checkingUpdates || !collection.repository}
                        onClick={() => onCheckCollection?.(collection)}
                        className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
                        {checkingUpdates ? '检查中…' : '检查更新'}
                      </button>
                      {missingCache ? <button type="button" onClick={() => onClone(missingCache.id, collection.name)}
                        className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-amber-700">恢复仓库缓存</button> : null}
                      {onSelect ? <button type="button" disabled={!selectedMembers.length || !onInstallSelection}
                        onClick={() => onInstallSelection?.(selectedMembers.map(s => s.id))}
                        className="rounded-md bg-sky-600 px-3 py-1.5 font-medium text-white hover:bg-sky-700 disabled:opacity-40">
                        安装所选（{selectedMembers.length}）
                      </button> : null}
                    </div>
                  </div>
                  <ul className={SKILL_GRID_CLASS}>{collection.visibleMembers.map(skill => renderSkill(skill, true))}</ul>
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <ul className={SKILL_GRID_CLASS}>
      {skills.map(skill => renderSkill(skill))}
    </ul>
  );
}
