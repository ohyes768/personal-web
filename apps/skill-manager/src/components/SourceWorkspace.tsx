'use client';

import { useMemo, useState } from 'react';
import ConfirmActionDialog from '@/components/ConfirmActionDialog';
import PublishQueue from '@/components/PublishQueue';
import SkillFilters, { DEFAULT_FILTERS, type FilterState } from '@/components/SkillFilters';
import SkillPool from '@/components/SkillPool';
import { ApiClientError, publish, publishPlan } from '@/lib/api';
import {
  addQueueTarget,
  clearQueue,
  removeQueueItem,
  removeQueueTarget,
  type QueueEntry,
  type TargetKey,
} from '@/lib/queue';
import type { PlanItem, PublishResultItem, SkillCard } from '@/lib/types';

export interface Notice {
  kind: 'ok' | 'err';
  text: string;
}

interface SourceWorkspaceProps {
  source: SkillCard['source'];
  skills: SkillCard[];
  loading: boolean;
  onRefresh: () => Promise<void>;
  onNotify: (notice: Notice | null) => void;
  onClone: (skillId: string, skillName: string) => void;
  onDelete: (skill: SkillCard) => void;
  onUnpublish: (skillId: string, skillName: string, targets: TargetKey[]) => void;
}

function applyFilters(skills: SkillCard[], filters: FilterState): SkillCard[] {
  const query = filters.query.trim().toLowerCase();
  return skills.filter((skill) => {
    if (query) {
      const haystack = `${skill.name} ${skill.id} ${skill.summary}`.toLowerCase();
      if (!haystack.includes(query)) {
        return false;
      }
    }
    if (filters.tags.some((tag) => !skill.tags.includes(tag))) {
      return false;
    }
    // "已发布"只认 status=active 的部署记录；下架后记录仍在（status=removed）
    const hasActiveDeployment = Object.values(skill.deployments).some(
      (deployment) => deployment.status === 'active'
    );
    if (filters.deployment === 'published' && !hasActiveDeployment) {
      return false;
    }
    if (filters.deployment === 'unpublished' && hasActiveDeployment) {
      return false;
    }
    if (filters.update === 'has_update' && !skill.update?.has_update) {
      return false;
    }
    if (filters.update === 'no_update' && skill.update?.has_update) {
      return false;
    }
    return true;
  });
}

/** 把计划中可发布的项（add/update）重新按 skill 分组为请求结构。 */
function planToRequests(items: PlanItem[]): { skill_id: string; targets: TargetKey[] }[] {
  const grouped = new Map<string, TargetKey[]>();
  for (const item of items) {
    if (item.action !== 'add' && item.action !== 'update') {
      continue;
    }
    grouped.set(item.skill_id, [...(grouped.get(item.skill_id) ?? []), item.target]);
  }
  return [...grouped].map(([skill_id, targets]) => ({ skill_id, targets }));
}

/** 单来源管理两件套：Skill 池 + 独立发布队列（自包含状态与发布确认弹窗）。 */
export default function SourceWorkspace({
  source,
  skills,
  loading,
  onRefresh,
  onNotify,
  onClone,
  onDelete,
  onUnpublish,
}: SourceWorkspaceProps) {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [plan, setPlan] = useState<PlanItem[] | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [results, setResults] = useState<PublishResultItem[] | null>(null);
  const [showPublishConfirm, setShowPublishConfirm] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const skillNames = useMemo(
    () => new Map(skills.map((skill) => [skill.id, skill.name])),
    [skills]
  );

  const allTags = useMemo(() => {
    const tags = new Set<string>();
    for (const skill of skills) {
      for (const tag of skill.tags) {
        tags.add(tag);
      }
    }
    return [...tags].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  }, [skills]);

  const filteredSkills = useMemo(() => applyFilters(skills, filters), [skills, filters]);

  function handleToggleQueueTarget(skillId: string, target: TargetKey) {
    const queued = queue.find((entry) => entry.skillId === skillId)?.targets.includes(target);
    setQueue((prev) =>
      queued ? removeQueueTarget(prev, skillId, target) : addQueueTarget(prev, skillId, target)
    );
    onNotify(null);
  }

  async function handleGeneratePlan() {
    if (queue.length === 0 || planLoading) {
      return;
    }
    setPlanLoading(true);
    setResults(null);
    onNotify(null);
    try {
      const response = await publishPlan(
        queue.map((entry) => ({ skill_id: entry.skillId, targets: entry.targets }))
      );
      setPlan(response.items);
    } catch (err) {
      onNotify({
        kind: 'err',
        text: err instanceof Error ? err.message : '生成发布计划失败',
      });
      setPlan(null);
    } finally {
      setPlanLoading(false);
    }
  }

  function handleConfirmPublish() {
    const publishable = plan?.filter(
      (item) => item.action === 'add' || item.action === 'update'
    );
    if (!plan || !publishable || publishable.length === 0) {
      return;
    }
    setActionError('');
    setShowPublishConfirm(true);
  }

  async function performPublish(password: string) {
    if (!plan) {
      return;
    }
    setActionBusy(true);
    setActionError('');
    try {
      const response = await publish(planToRequests(plan), password);
      setResults(response.items);
      setQueue([]);
      setPlan([]);
      setShowPublishConfirm(false);
      const failed = response.items.filter((item) => item.status !== 'success');
      onNotify(
        failed.length === 0
          ? { kind: 'ok', text: `发布完成：${response.items.length} 项全部成功` }
          : { kind: 'err', text: `发布完成：${failed.length} 项失败，详见结果列表` }
      );
      await onRefresh();
    } catch (err) {
      setActionError(
        err instanceof ApiClientError || err instanceof Error ? err.message : '发布失败'
      );
    } finally {
      setActionBusy(false);
    }
  }

  const publishableItems = plan?.filter(
    (item) => item.action === 'add' || item.action === 'update'
  );
  const planAddCount = plan?.filter((item) => item.action === 'add').length ?? 0;
  const planUpdateCount = plan?.filter((item) => item.action === 'update').length ?? 0;

  return (
    <div
      data-source={source}
      className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]"
    >
      {/* 左：Skill 池 */}
      <section className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
        <SkillFilters
          value={filters}
          allTags={allTags}
          onChange={setFilters}
          showUpdateFilter={source === 'github'}
        />
        {loading ? (
          <p className="p-6 text-center text-sm text-slate-400">加载中…</p>
        ) : (
          <SkillPool
            skills={filteredSkills}
            queue={queue}
            onToggleQueueTarget={handleToggleQueueTarget}
            onClone={onClone}
            onDelete={onDelete}
            onUnpublish={onUnpublish}
          />
        )}
      </section>

      {/* 右：发布队列（每来源独立） */}
      <section className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
        <PublishQueue
          queue={queue}
          skillNames={skillNames}
          plan={plan}
          planLoading={planLoading}
          publishing={actionBusy}
          results={results}
          onRemoveItem={(skillId) => setQueue((prev) => removeQueueItem(prev, skillId))}
          onRemoveTarget={(skillId, target) =>
            setQueue((prev) => removeQueueTarget(prev, skillId, target))
          }
          onClear={() => setQueue((prev) => clearQueue(prev))}
          onGeneratePlan={() => void handleGeneratePlan()}
          onConfirmPublish={handleConfirmPublish}
        />
      </section>

      {showPublishConfirm && publishableItems && publishableItems.length > 0 ? (
        <ConfirmActionDialog
          title="确认发布"
          description={
            <div className="space-y-1">
              <p className="font-medium">
                新增 {planAddCount} 项 · 更新 {planUpdateCount} 项
              </p>
              <ul className="list-disc space-y-0.5 pl-4">
                {publishableItems.map((item) => (
                  <li key={`${item.skill_id}-${item.target}`}>
                    {skillNames.get(item.skill_id) ?? item.skill_id} →{' '}
                    {item.target === 'openclaw' ? 'OpenClaw' : 'Hermes'}
                    （{item.action === 'add' ? '新增' : '更新'}）
                  </li>
                ))}
              </ul>
            </div>
          }
          confirmLabel="执行发布"
          busy={actionBusy}
          error={actionError}
          onConfirm={(password) => void performPublish(password)}
          onCancel={() => setShowPublishConfirm(false)}
        />
      ) : null}
    </div>
  );
}
