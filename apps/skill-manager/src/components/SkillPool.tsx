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
  onRollback: (skillId: string, target: TargetKey) => void;
  onUnpublish: (skillId: string, target: TargetKey) => void;
}

function DeploymentBadge({ deployment }: { deployment?: TargetDeployment }) {
  if (!deployment) {
    return <span className="text-xs text-slate-400">未发布</span>;
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

/** 左栏单张 Skill 卡片：target 多选 chips + 加入队列；部署行内联回滚/下架。 */
function SkillCardItem({
  skill,
  queuedTargets,
  onAddToQueue,
  onRollback,
  onUnpublish,
}: {
  skill: SkillCard;
  queuedTargets: TargetKey[];
  onAddToQueue: SkillPoolProps['onAddToQueue'];
  onRollback: SkillPoolProps['onRollback'];
  onUnpublish: SkillPoolProps['onUnpublish'];
}) {
  const [selectedTargets, setSelectedTargets] = useState<TargetKey[]>([]);

  function toggleTarget(target: TargetKey) {
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
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
              有更新
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

      {/* 部署状态 + 回滚/下架 */}
      <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
        {ALL_TARGETS.map((target) => {
          const deployment = skill.deployments[target];
          const deployed = Boolean(deployment);
          return (
            <div key={target} className="flex items-center justify-between gap-2 text-xs">
              <span className="flex items-center gap-2">
                <span className="w-16 text-slate-500">{TARGET_LABEL[target]}</span>
                <DeploymentBadge deployment={deployment} />
              </span>
              {deployed ? (
                <span className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => onRollback(skill.id, target)}
                    className="rounded border border-slate-300 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    回滚
                  </button>
                  <button
                    type="button"
                    onClick={() => onUnpublish(skill.id, target)}
                    className="rounded border border-rose-200 px-1.5 py-0.5 text-xs text-rose-600 hover:bg-rose-50"
                  >
                    下架
                  </button>
                </span>
              ) : null}
            </div>
          );
        })}
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
              disabled={queued}
              onClick={() => toggleTarget(target)}
              className={`rounded px-2 py-0.5 text-xs ${
                queued
                  ? 'bg-emerald-50 text-emerald-600'
                  : selected
                    ? 'bg-sky-600 text-white'
                    : 'border border-slate-300 text-slate-600 hover:bg-slate-50'
              } disabled:cursor-not-allowed`}
              title={queued ? '已在发布队列中' : undefined}
            >
              {queued ? `${TARGET_LABEL[target]} 已在队列` : TARGET_LABEL[target]}
            </button>
          );
        })}
        <button
          type="button"
          disabled={selectedTargets.length === 0}
          onClick={() => {
            onAddToQueue(skill.id, selectedTargets);
            setSelectedTargets([]);
          }}
          className="ml-auto rounded bg-sky-600 px-2.5 py-1 text-xs text-white hover:bg-sky-700 disabled:opacity-40"
        >
          加入队列
        </button>
      </div>
    </li>
  );
}

export default function SkillPool({
  skills,
  queue,
  onAddToQueue,
  onRollback,
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
    <ul className="space-y-2">
      {skills.map((skill) => (
        <SkillCardItem
          key={skill.id}
          skill={skill}
          queuedTargets={queuedBySkill.get(skill.id) ?? []}
          onAddToQueue={onAddToQueue}
          onRollback={onRollback}
          onUnpublish={onUnpublish}
        />
      ))}
    </ul>
  );
}
