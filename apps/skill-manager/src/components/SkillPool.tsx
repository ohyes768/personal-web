'use client';

import type { ReactNode } from 'react';
import type { QueueEntry, TargetKey } from '@/lib/queue';
import type { SkillCard, TargetDeployment } from '@/lib/types';
import { shortRepo } from '@/lib/format';
import {
  CrayfishIcon,
  DownloadIcon,
  HermesIcon,
  TrashIcon,
  UnlinkIcon,
} from '@/components/icons';

const ALL_TARGETS: TargetKey[] = ['openclaw', 'hermes'];

const TARGET_LABEL: Record<TargetKey, string> = {
  openclaw: 'OpenClaw',
  hermes: 'Hermes',
};

/** target 队列 chip 的品牌语义色：OpenClaw=螯红、Hermes=神使蓝。 */
const TARGET_ICON: Record<TargetKey, { icon: ReactNode; hover: string }> = {
  openclaw: { icon: <CrayfishIcon />, hover: 'hover:text-rose-600' },
  hermes: { icon: <HermesIcon />, hover: 'hover:text-sky-600' },
};

interface SkillPoolProps {
  skills: SkillCard[];
  queue: QueueEntry[];
  onToggleQueueTarget: (skillId: string, target: TargetKey) => void;
  onClone: (skillId: string, skillName: string) => void;
  onDelete: (skill: SkillCard) => void;
  onUnpublish: (skillId: string, skillName: string, targets: TargetKey[]) => void;
}

function DeploymentBadge({ deployment }: { deployment?: TargetDeployment }) {
  if (!deployment) {
    return <span className="text-xs text-slate-400">未发布</span>;
  }
  if (deployment.status === 'active' && deployment.link_missing) {
    return (
      <span
        className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700"
        title="账本记录已发布，但目标目录的链接已不存在（可能被手动删除）；生成发布计划会按实况判定动作"
      >
        已发布 · 链接缺失
      </span>
    );
  }
  if (deployment.status === 'active') {
    return (
      <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">
        已发布{deployment.revision ? ` · ${deployment.revision.slice(0, 7)}` : ''}
      </span>
    );
  }
  return (
    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">
      {deployment.status}
    </span>
  );
}

/** 左栏单张 Skill 卡片：target 点击即切换入队/出队；部署状态只读徽章。 */
function SkillCardItem({
  skill,
  queuedTargets,
  onToggleQueueTarget,
  onClone,
  onDelete,
  onUnpublish,
}: {
  skill: SkillCard;
  queuedTargets: TargetKey[];
  onToggleQueueTarget: SkillPoolProps['onToggleQueueTarget'];
  onClone: SkillPoolProps['onClone'];
  onDelete: SkillPoolProps['onDelete'];
  onUnpublish: SkillPoolProps['onUnpublish'];
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
        <div className="mt-1.5 flex flex-wrap gap-1">
          {skill.tags.map((tag) => (
            <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {/* 部署状态（只读徽章） */}
      <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
        {ALL_TARGETS.map((target) => (
          <div key={target} className="flex items-center gap-2 text-xs">
            <span className="w-16 text-slate-500">{TARGET_LABEL[target]}</span>
            <DeploymentBadge deployment={skill.deployments[target]} />
          </div>
        ))}
      </div>

      {/* 加入队列：target 图标 chip，点击即切换入队/出队（贴卡片底部） */}
      <div className="mt-auto flex items-center gap-2 border-t border-slate-100 pt-2">
        {ALL_TARGETS.map((target) => {
          const queued = queuedTargets.includes(target);
          const { icon, hover } = TARGET_ICON[target];
          return (
            <button
              key={target}
              type="button"
              aria-label={`${TARGET_LABEL[target]} ${queued ? '已在队列，点击移出' : '点击加入队列'}`}
              data-tip={
                publishBlocked
                  ? sourceMissing
                    ? '源缺失，无法发布'
                    : '请先 Clone 缓存'
                  : queued
                    ? `移出 ${TARGET_LABEL[target]} 队列`
                    : `加入 ${TARGET_LABEL[target]} 队列`
              }
              title={
                publishBlocked
                  ? sourceMissing
                    ? '源库登记目录缺失，无法发布'
                    : '请先 Clone 缓存'
                  : queued
                    ? `点击移出 ${TARGET_LABEL[target]} 发布队列`
                    : `点击加入 ${TARGET_LABEL[target]} 发布队列`
              }
              disabled={publishBlocked}
              onClick={() => onToggleQueueTarget(skill.id, target)}
              className={`icon-btn tip-left rounded-md border transition-colors ${
                queued
                  ? 'border-emerald-500 bg-emerald-500 text-white'
                  : `border-slate-300 bg-white ${hover}`
              }`}
            >
              {icon}
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
            data-tip="Clone 缓存（发布前必做）"
            title="从 GitHub 拉取仓库到本机缓存，发布前必做"
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
  queue,
  onToggleQueueTarget,
  onClone,
  onDelete,
  onUnpublish,
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

  return (
    <ul className="grid grid-cols-1 items-stretch gap-2.5 md:grid-cols-2 lg:grid-cols-3">
      {skills.map((skill) => (
        <SkillCardItem
          key={skill.id}
          skill={skill}
          queuedTargets={queuedBySkill.get(skill.id) ?? []}
          onToggleQueueTarget={onToggleQueueTarget}
          onClone={onClone}
          onDelete={onDelete}
          onUnpublish={onUnpublish}
        />
      ))}
    </ul>
  );
}
