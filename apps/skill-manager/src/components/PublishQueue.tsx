'use client';

import type { QueueEntry, TargetKey } from '@/lib/queue';
import type { PlanItem, PublishResultItem } from '@/lib/types';

const TARGET_LABEL: Record<TargetKey, string> = {
  openclaw: 'OpenClaw',
  hermes: 'Hermes',
};

const ACTION_META: Record<PlanItem['action'], { label: string; className: string }> = {
  add: { label: '新增', className: 'bg-emerald-50 text-emerald-700' },
  update: { label: '更新', className: 'bg-sky-50 text-sky-700' },
  unchanged: { label: '无需操作', className: 'bg-slate-100 text-slate-500' },
  blocked: { label: '已阻止', className: 'bg-rose-50 text-rose-700' },
};

const RESULT_META: Record<PublishResultItem['status'], string> = {
  success: 'bg-emerald-50 text-emerald-700',
  blocked: 'bg-amber-50 text-amber-700',
  error: 'bg-rose-50 text-rose-700',
};

interface PublishQueueProps {
  queue: QueueEntry[];
  skillNames: Map<string, string>;
  plan: PlanItem[] | null;
  planLoading: boolean;
  publishing: boolean;
  results: PublishResultItem[] | null;
  onRemoveItem: (skillId: string) => void;
  onRemoveTarget: (skillId: string, target: TargetKey) => void;
  onClear: () => void;
  onGeneratePlan: () => void;
  onConfirmPublish: () => void;
}

/** 右栏发布队列（design 4.2）：瞬时选择状态，移除绝不触发任何写接口。 */
export default function PublishQueue({
  queue,
  skillNames,
  plan,
  planLoading,
  publishing,
  results,
  onRemoveItem,
  onRemoveTarget,
  onClear,
  onGeneratePlan,
  onConfirmPublish,
}: PublishQueueProps) {
  const publishableCount =
    plan?.filter((item) => item.action === 'add' || item.action === 'update').length ?? 0;

  return (
    <div className="flex h-full flex-col gap-3">
      <section className="rounded-lg border border-slate-200 bg-white">
        <header className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
          <h2 className="text-sm font-semibold text-slate-700">
            发布队列（{queue.length}）
          </h2>
          {queue.length > 0 ? (
            <button
              type="button"
              onClick={onClear}
              disabled={publishing}
              className="text-xs text-slate-400 underline hover:text-slate-600"
            >
              清空
            </button>
          ) : null}
        </header>
        {queue.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-slate-400">
            从左栏把 Skill 加入本次发布队列；移出队列不会影响已部署的 Skill
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {queue.map((entry) => (
              <li key={entry.skillId} className="flex items-center justify-between gap-2 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm text-slate-700">
                    {skillNames.get(entry.skillId) ?? entry.skillId}
                  </p>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {entry.targets.map((target) => (
                      <span
                        key={target}
                        className="flex items-center gap-1 rounded bg-sky-50 px-1.5 py-0.5 text-xs text-sky-700"
                      >
                        {TARGET_LABEL[target]}
                        <button
                          type="button"
                          aria-label={`移除 ${TARGET_LABEL[target]}`}
                          disabled={publishing}
                          onClick={() => onRemoveTarget(entry.skillId, target)}
                          className="text-sky-400 hover:text-sky-700"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={publishing}
                  onClick={() => onRemoveItem(entry.skillId)}
                  className="shrink-0 rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-500 hover:bg-slate-50"
                >
                  移出
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex gap-2">
        <button
          type="button"
          disabled={queue.length === 0 || planLoading || publishing}
          onClick={onGeneratePlan}
          className="flex-1 rounded border border-sky-600 px-3 py-1.5 text-sm text-sky-700 hover:bg-sky-50 disabled:opacity-40"
        >
          {planLoading ? '计算计划中…' : '生成发布计划'}
        </button>
        <button
          type="button"
          disabled={publishableCount === 0 || publishing}
          onClick={onConfirmPublish}
          className="flex-1 rounded bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-700 disabled:opacity-40"
        >
          确认发布{publishableCount > 0 ? `（${publishableCount} 项）` : ''}
        </button>
      </div>

      {plan ? (
        <section className="flex-1 overflow-y-auto rounded-lg border border-slate-200 bg-white">
          <header className="border-b border-slate-100 px-3 py-2">
            <h2 className="text-sm font-semibold text-slate-700">发布计划预览（只读）</h2>
          </header>
          <ul className="divide-y divide-slate-100">
            {plan.map((item) => {
              const meta = ACTION_META[item.action];
              return (
                <li key={`${item.skill_id}-${item.target}`} className="px-3 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-slate-700">
                      {skillNames.get(item.skill_id) ?? item.skill_id} → {TARGET_LABEL[item.target]}
                    </span>
                    <span className={`shrink-0 rounded px-1.5 py-0.5 ${meta.className}`}>
                      {meta.label}
                    </span>
                  </div>
                  {item.action === 'blocked' && item.reason ? (
                    <p className="mt-1 text-rose-600">{item.reason}</p>
                  ) : null}
                  {item.action === 'update' ? (
                    <p className="mt-0.5 text-slate-400">
                      {item.current_revision.slice(0, 7) || '未知'} →{' '}
                      {item.planned_revision.slice(0, 7) || '未知'}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {results ? (
        <section className="rounded-lg border border-slate-200 bg-white">
          <header className="border-b border-slate-100 px-3 py-2">
            <h2 className="text-sm font-semibold text-slate-700">发布结果</h2>
          </header>
          <ul className="divide-y divide-slate-100">
            {results.map((item) => (
              <li key={`${item.skill_id}-${item.target}`} className="px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-slate-700">
                    {skillNames.get(item.skill_id) ?? item.skill_id} → {TARGET_LABEL[item.target]}
                  </span>
                  <span className={`shrink-0 rounded px-1.5 py-0.5 ${RESULT_META[item.status]}`}>
                    {item.status === 'success' ? '成功' : item.status === 'blocked' ? '被阻止' : '失败'}
                  </span>
                </div>
                {item.error ? <p className="mt-1 text-rose-600">{item.error}</p> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
