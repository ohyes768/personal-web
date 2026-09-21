'use client';

import { useMemo } from 'react';
import type { TargetKey } from '@/lib/queue';
import type { SkillCard } from '@/lib/types';

const ALL_TARGETS: TargetKey[] = ['openclaw', 'hermes'];

const TARGET_LABEL: Record<TargetKey, string> = {
  openclaw: 'OpenClaw',
  hermes: 'Hermes',
};

interface DeployedItem {
  skillId: string;
  skillName: string;
  revision: string;
  publishedAt: string;
}

interface DeployedViewProps {
  skills: SkillCard[];
  onRollback: (skillId: string, target: TargetKey) => void;
  onUnpublish: (skillId: string, target: TargetKey) => void;
}

function formatPublishedAt(value: string): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('zh-CN', { hour12: false });
}

/** 右栏已部署视图（R1）：按 target 分组展示 status=active 的部署，回滚/下架唯一入口。 */
export default function DeployedView({ skills, onRollback, onUnpublish }: DeployedViewProps) {
  const deployedByTarget = useMemo(() => {
    const result: Record<TargetKey, DeployedItem[]> = { openclaw: [], hermes: [] };
    for (const skill of skills) {
      for (const target of ALL_TARGETS) {
        const deployment = skill.deployments[target];
        if (deployment?.status === 'active') {
          result[target].push({
            skillId: skill.id,
            skillName: skill.name,
            revision: deployment.revision,
            publishedAt: deployment.published_at,
          });
        }
      }
    }
    return result;
  }, [skills]);

  return (
    <div className="flex flex-col gap-3">
      {ALL_TARGETS.map((target) => {
        const items = deployedByTarget[target];
        return (
          <section key={target} className="rounded-lg border border-slate-200 bg-white">
            <header className="border-b border-slate-100 px-3 py-2">
              <h2 className="text-sm font-semibold text-slate-700">
                {TARGET_LABEL[target]}（{items.length}）
              </h2>
            </header>
            {items.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-slate-400">
                {TARGET_LABEL[target]} 暂无已部署的 Skill
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {items.map((item) => (
                  <li
                    key={item.skillId}
                    className="flex items-center justify-between gap-2 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm text-slate-700">{item.skillName}</p>
                      <p className="mt-0.5 text-xs text-slate-400">
                        {[item.revision.slice(0, 7), formatPublishedAt(item.publishedAt)]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        onClick={() => onRollback(item.skillId, target)}
                        className="rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                      >
                        回滚
                      </button>
                      <button
                        type="button"
                        onClick={() => onUnpublish(item.skillId, target)}
                        className="rounded border border-rose-200 px-2 py-0.5 text-xs text-rose-600 hover:bg-rose-50"
                      >
                        下架
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
