'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import DeployedView from '@/components/DeployedView';
import PublishQueue from '@/components/PublishQueue';
import RegisterGithubDialog from '@/components/RegisterGithubDialog';
import ConfirmActionDialog from '@/components/ConfirmActionDialog';
import SkillFilters, { DEFAULT_FILTERS, type FilterState } from '@/components/SkillFilters';
import SkillPool from '@/components/SkillPool';
import {
  ApiClientError,
  checkUpdates,
  cloneGithubCache,
  listSkills,
  publish,
  publishPlan,
  registerGithubSkill,
  rollbackSkill,
  unpublishSkill,
} from '@/lib/api';
import {
  addQueueTarget,
  clearQueue,
  removeQueueItem,
  removeQueueTarget,
  type QueueEntry,
  type TargetKey,
} from '@/lib/queue';
import type {
  PlanItem,
  PublishResultItem,
  RegisterGithubSkillInput,
  SkillCard,
} from '@/lib/types';

const TARGET_LABEL: Record<TargetKey, string> = {
  openclaw: 'OpenClaw',
  hermes: 'Hermes',
};

interface Notice {
  kind: 'ok' | 'err';
  text: string;
}

interface PendingTargetOp {
  kind: 'rollback' | 'unpublish';
  skillId: string;
  skillName: string;
  target: TargetKey;
}

/** 待 Clone 缓存的 GitHub Skill（缓存缺失，发布前必须先重建缓存）。 */
interface PendingClone {
  skillId: string;
  skillName: string;
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
    if (filters.source !== 'all' && skill.source !== filters.source) {
      return false;
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
    if (filters.status !== 'all' && skill.status !== filters.status) {
      return false;
    }
    return true;
  });
}

function publishableCount(items: PlanItem[]): number {
  return items.filter((item) => item.action === 'add' || item.action === 'update').length;
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

export default function Page() {
  const [skills, setSkills] = useState<SkillCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [checkingUpdates, setCheckingUpdates] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [plan, setPlan] = useState<PlanItem[] | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [results, setResults] = useState<PublishResultItem[] | null>(null);

  const [showPublishConfirm, setShowPublishConfirm] = useState(false);
  const [showRegister, setShowRegister] = useState(false);
  const [pendingOp, setPendingOp] = useState<PendingTargetOp | null>(null);
  const [pendingClone, setPendingClone] = useState<PendingClone | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const skillNames = useMemo(
    () => new Map(skills.map((skill) => [skill.id, skill.name])),
    [skills]
  );

  const refreshSkills = useCallback(async () => {
    try {
      const response = await listSkills();
      setSkills(response.items);
      setLoadError('');
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : '加载 Skill 列表失败');
    }
  }, []);

  useEffect(() => {
    void refreshSkills().finally(() => setLoading(false));
  }, [refreshSkills]);

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

  function handleAddToQueue(skillId: string, targets: TargetKey[]) {
    setQueue((prev) => targets.reduce((acc, t) => addQueueTarget(acc, skillId, t), prev));
    setNotice(null);
  }

  async function handleCheckUpdates() {
    setCheckingUpdates(true);
    setNotice(null);
    try {
      const response = await checkUpdates([]);
      // check-updates 是只读端点，检查结果由前端合并进卡片
      setSkills((prev) =>
        prev.map((skill) => {
          const item = response.items.find((i) => i.skill_id === skill.id);
          return item && item.result === 'ok' && item.info
            ? { ...skill, update: item.info }
            : skill;
        })
      );
      const updatable = response.items.filter((i) => i.result === 'ok' && i.info?.has_update);
      setNotice({
        kind: 'ok',
        text: `检查完成：${updatable.length} 个 GitHub Skill 有远端更新`,
      });
    } catch (err) {
      setNotice({
        kind: 'err',
        text: err instanceof Error ? err.message : '检查更新失败',
      });
    } finally {
      setCheckingUpdates(false);
    }
  }

  async function handleGeneratePlan() {
    if (queue.length === 0 || planLoading) {
      return;
    }
    setPlanLoading(true);
    setResults(null);
    setNotice(null);
    try {
      const response = await publishPlan(
        queue.map((entry) => ({ skill_id: entry.skillId, targets: entry.targets }))
      );
      setPlan(response.items);
    } catch (err) {
      setNotice({
        kind: 'err',
        text: err instanceof Error ? err.message : '生成发布计划失败',
      });
      setPlan(null);
    } finally {
      setPlanLoading(false);
    }
  }

  function handleConfirmPublish() {
    if (!plan || publishableCount(plan) === 0) {
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
      setNotice(
        failed.length === 0
          ? { kind: 'ok', text: `发布完成：${response.items.length} 项全部成功` }
          : { kind: 'err', text: `发布完成：${failed.length} 项失败，详见右栏结果` }
      );
      await refreshSkills();
    } catch (err) {
      setActionError(
        err instanceof ApiClientError || err instanceof Error
          ? err.message
          : '发布失败'
      );
    } finally {
      setActionBusy(false);
    }
  }

  async function performTargetOp(password: string) {
    if (!pendingOp) {
      return;
    }
    setActionBusy(true);
    setActionError('');
    try {
      if (pendingOp.kind === 'rollback') {
        await rollbackSkill(pendingOp.skillId, pendingOp.target, password);
        setNotice({
          kind: 'ok',
          text: `${pendingOp.skillName} 已回滚（${TARGET_LABEL[pendingOp.target]}）`,
        });
      } else {
        await unpublishSkill(pendingOp.skillId, pendingOp.target, password);
        setNotice({
          kind: 'ok',
          text: `${pendingOp.skillName} 已下架（${TARGET_LABEL[pendingOp.target]}）`,
        });
      }
      setPendingOp(null);
      await refreshSkills();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '操作失败');
    } finally {
      setActionBusy(false);
    }
  }

  async function performRegister(input: RegisterGithubSkillInput, password: string) {
    setActionBusy(true);
    setActionError('');
    try {
      await registerGithubSkill(input, password);
      setShowRegister(false);
      setNotice({ kind: 'ok', text: `已登记 GitHub Skill「${input.name}」` });
      await refreshSkills();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '登记失败');
    } finally {
      setActionBusy(false);
    }
  }

  async function performClone(password: string) {
    if (!pendingClone) {
      return;
    }
    setActionBusy(true);
    setActionError('');
    try {
      await cloneGithubCache(pendingClone.skillId, password);
      setPendingClone(null);
      setNotice({ kind: 'ok', text: `「${pendingClone.skillName}」缓存已就绪` });
      await refreshSkills();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Clone 失败');
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
    <main className="mx-auto flex h-screen max-w-7xl flex-col gap-3 p-4">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-800">Skill 发布管理台</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleCheckUpdates}
            disabled={checkingUpdates}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {checkingUpdates ? '检查中…' : '检查 GitHub 更新'}
          </button>
          <button
            type="button"
            onClick={() => {
              setActionError('');
              setShowRegister(true);
            }}
            className="rounded bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-800"
          >
            新增 GitHub Skill
          </button>
        </div>
      </header>

      {loadError ? (
        <p className="rounded bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
          {loadError}
        </p>
      ) : null}
      {notice ? (
        <p
          className={`rounded px-3 py-2 text-sm ${
            notice.kind === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
          }`}
          role="status"
        >
          {notice.text}
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]">
        {/* 左栏：可用 Skill 池 */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          <SkillFilters value={filters} allTags={allTags} onChange={setFilters} />
          {loading ? (
            <p className="p-6 text-center text-sm text-slate-400">加载中…</p>
          ) : (
            <SkillPool
              skills={filteredSkills}
              queue={queue}
              onAddToQueue={handleAddToQueue}
              onClone={(skillId) => {
                setActionError('');
                setPendingClone({
                  skillId,
                  skillName: skillNames.get(skillId) ?? skillId,
                });
              }}
            />
          )}
        </section>

        {/* 右栏：已部署视图（主体）+ 发布队列（辅助） */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          <DeployedView
            skills={skills}
            onRollback={(skillId, target) => {
              setActionError('');
              setPendingOp({
                kind: 'rollback',
                skillId,
                skillName: skillNames.get(skillId) ?? skillId,
                target,
              });
            }}
            onUnpublish={(skillId, target) => {
              setActionError('');
              setPendingOp({
                kind: 'unpublish',
                skillId,
                skillName: skillNames.get(skillId) ?? skillId,
                target,
              });
            }}
          />
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
      </div>

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
                    {TARGET_LABEL[item.target]}
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

      {pendingOp ? (
        <ConfirmActionDialog
          title={pendingOp.kind === 'rollback' ? '确认回滚' : '确认下架'}
          description={
            <p>
              {pendingOp.kind === 'rollback'
                ? `将把「${pendingOp.skillName}」在 ${TARGET_LABEL[pendingOp.target]} 上回滚到上一次成功版本。`
                : `将从 ${TARGET_LABEL[pendingOp.target]} 移除「${pendingOp.skillName}」的技能链接（不删除任何目录）。`}
            </p>
          }
          confirmLabel={pendingOp.kind === 'rollback' ? '执行回滚' : '确认下架'}
          busy={actionBusy}
          error={actionError}
          onConfirm={(password) => void performTargetOp(password)}
          onCancel={() => setPendingOp(null)}
        />
      ) : null}

      {pendingClone ? (
        <ConfirmActionDialog
          title="确认 Clone 缓存"
          description={
            <p>
              将从 GitHub 拉取「{pendingClone.skillName}
              」的仓库到本机缓存目录（只写缓存，不触碰已发布目标）。
              大仓库经代理可能需要数分钟，请耐心等待。
            </p>
          }
          confirmLabel="执行 Clone"
          busy={actionBusy}
          error={actionError}
          onConfirm={(password) => void performClone(password)}
          onCancel={() => setPendingClone(null)}
        />
      ) : null}

      {showRegister ? (
        <RegisterGithubDialog
          busy={actionBusy}
          error={actionError}
          onRegister={(input, password) => void performRegister(input, password)}
          onCancel={() => setShowRegister(false)}
        />
      ) : null}
    </main>
  );
}
