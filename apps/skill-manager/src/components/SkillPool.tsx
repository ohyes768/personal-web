'use client';

import { useState } from 'react';
import type { QueueEntry, TargetKey } from '@/lib/queue';
import type { SkillCard, TargetDeployment } from '@/lib/types';

const ALL_TARGETS: TargetKey[] = ['openclaw', 'hermes'];

const TARGET_LABEL: Record<TargetKey, string> = {
  openclaw: 'OpenClaw',
  hermes: 'Hermes',
};

interface SkillPoolProps {
  skills: SkillCard[];
  queue: QueueEntry[];
  onAddToQueue: (skillId: string, targets: TargetKey[]) => void;
  onClone: (skillId: string) => void;
  onDelete: (skill: SkillCard) => void;
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

/** 左栏单张 Skill 卡片：target 多选 chips + 加入队列；部署状态只读徽章。 */
function SkillCardItem({
  skill,
  queuedTargets,
  onAddToQueue,
  onClone,
  onDelete,
}: {
  skill: SkillCard;
  queuedTargets: TargetKey[];
  onAddToQueue: SkillPoolProps['onAddToQueue'];
  onClone: SkillPoolProps['onClone'];
  onDelete: SkillPoolProps['onDelete'];
}) {
  const [selectedTargets, setSelectedTargets] = useState<TargetKey[]>([]);
  const [targetHint, setTargetHint] = useState(false);
  const cacheMissing = skill.cache_missing;
  const sourceMissing = skill.source_missing;
  const publishBlocked = cacheMissing || sourceMissing;

  function toggleTarget(target: TargetKey) {
    setTargetHint(false);
    setSelectedTargets((prev) =>
      prev.includes(target) ? prev.filter((t) => t !== target) : [...prev, target]
    );
  }

  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-medium text-slate-800">{skill.name}</h3>
          <p className="text-xs text-slate-400">
            {skill.id} · {skill.source === 'local' ? '自研' : skill.repository}
          </p>
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

      {/* 部署状态（只读，回滚/下架入口在右栏已部署视图） */}
      <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
        {ALL_TARGETS.map((target) => (
          <div key={target} className="flex items-center gap-2 text-xs">
            <span className="w-16 text-slate-500">{TARGET_LABEL[target]}</span>
            <DeploymentBadge deployment={skill.deployments[target]} />
          </div>
        ))}
      </div>

      {/* 加入队列：target 多选 chips */}
      <div className="mt-2 flex items-center gap-2 border-t border-slate-100 pt-2">
        {ALL_TARGETS.map((target) => {
          const queued = queuedTargets.includes(target);
          const selected = selectedTargets.includes(target);
          return (
            <button
              key={target}
              type="button"
              disabled={queued || publishBlocked}
              onClick={() => toggleTarget(target)}
              className={`rounded px-2 py-0.5 text-xs ${
                queued
                  ? 'bg-emerald-50 text-emerald-600'
                  : selected
                    ? 'bg-sky-600 text-white'
                    : 'border border-slate-300 text-slate-600 hover:bg-slate-50'
              } disabled:cursor-not-allowed disabled:opacity-50`}
              title={
                queued
                  ? '已在发布队列中'
                  : sourceMissing
                    ? '源库登记目录缺失，无法发布'
                    : cacheMissing
                      ? '请先 Clone 缓存'
                      : undefined
              }
            >
              {queued ? `${TARGET_LABEL[target]} 已在队列` : TARGET_LABEL[target]}
            </button>
          );
        })}
        <button
          type="button"
          disabled={publishBlocked}
          onClick={() => {
            if (selectedTargets.length === 0) {
              setTargetHint(true);
              return;
            }
            onAddToQueue(skill.id, selectedTargets);
            setSelectedTargets([]);
          }}
          title={
            sourceMissing
              ? '源库登记目录缺失，无法发布'
              : cacheMissing
                ? '请先 Clone 缓存'
                : undefined
          }
          className="ml-auto rounded bg-sky-600 px-2.5 py-1 text-xs text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          加入队列
        </button>
        {skill.source === 'github' ? (
          <button
            type="button"
            onClick={() => onDelete(skill)}
            title="移除登记条目并删除本机缓存"
            className="rounded border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
          >
            删除
          </button>
        ) : null}
      </div>
      {targetHint ? (
        <p className="mt-1 text-xs text-rose-600">请先选择发布目标（OpenClaw / Hermes）</p>
      ) : null}
      {cacheMissing ? (
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2">
          <span className="text-xs text-amber-700">
            缓存缺失：本环境没有该 Skill 的 GitHub 缓存，无法发布
          </span>
          <button
            type="button"
            onClick={() => onClone(skill.id)}
            className="shrink-0 rounded bg-amber-600 px-2.5 py-1 text-xs text-white hover:bg-amber-700"
          >
            Clone
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
  onAddToQueue,
  onClone,
  onDelete,
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
    <ul className="space-y-2">
      {skills.map((skill) => (
        <SkillCardItem
          key={skill.id}
          skill={skill}
          queuedTargets={queuedBySkill.get(skill.id) ?? []}
          onAddToQueue={onAddToQueue}
          onClone={onClone}
          onDelete={onDelete}
        />
      ))}
    </ul>
  );
}
