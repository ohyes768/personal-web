'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import ConfirmActionDialog from '@/components/ConfirmActionDialog';
import DeployBoard from '@/components/DeployBoard';
import ExportTargetManager from '@/components/ExportTargetManager';
import RegisterGithubDialog from '@/components/RegisterGithubDialog';
import SourceWorkspace, { type Notice } from '@/components/SourceWorkspace';
import TaskProgressDialog from '@/components/TaskProgressDialog';
import {
  checkUpdates,
  cloneGithubCache,
  deleteSkill,
  listSkills,
  listExportTargets,
  unpublishSkill,
} from '@/lib/api';
import type { TargetKey } from '@/lib/queue';
import { runUnpublishBatch, type UnpublishItem, type UnpublishResult } from '@/lib/batchActions';
import { groupCollections } from '@/lib/collections';
import type {
  ExportTarget,
  SkillCard,
  TaskSnapshot,
} from '@/lib/types';

type ViewKey = 'manage' | 'board' | 'targets';
type SourceTab = 'local' | 'github';

import { TARGET_LABEL } from '@/lib/targets';

const SEG_BUTTON =
  'rounded px-3 py-1.5 text-sm transition-colors data-[active=true]:bg-white data-[active=true]:font-medium data-[active=true]:text-slate-800 data-[active=true]:shadow-sm text-slate-500 hover:text-slate-700';

interface PendingUnpublish {
  name: string;
  items: UnpublishItem[];
  results: UnpublishResult[];
}

/** 待 Clone 缓存的 GitHub Skill（缓存缺失，发布前必须先重建缓存）。 */
interface PendingClone {
  skillId: string;
  skillName: string;
}

/** 待删除登记的 GitHub Skill（移除 registry 条目并清理本机缓存）。 */
interface PendingDelete {
  skillId: string;
  skillName: string;
}

/** 进行中的 GitHub 后台任务（登记/Clone，PRD R2/R3），进度弹窗展示其快照。 */
interface ActiveGithubTask {
  taskId: string;
  title: string;
  successNotice: string;
}

function SkillManagerPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // 两级导航：URL 是唯一真源，非法值在派生时逐级回退
  const view: ViewKey = searchParams.get('view') === 'board' ? 'board' : searchParams.get('view') === 'targets' ? 'targets' : 'manage';
  const sourceTab: SourceTab = searchParams.get('tab') === 'github' ? 'github' : 'local';
  const agent: TargetKey = 'hermes';

  function navigate(next: { view?: ViewKey; tab?: SourceTab; agent?: TargetKey }) {
    const p = new URLSearchParams(searchParams.toString());
    const v = next.view ?? view;
    p.set('view', v);
    if (v === 'manage') {
      p.set('tab', next.tab ?? (v === view ? sourceTab : 'local'));
      p.delete('agent');
    } else if (v === 'board') {
      p.set('agent', next.agent ?? (v === view ? agent : 'hermes'));
      p.delete('tab');
    } else {
      p.delete('tab');
      p.delete('agent');
    }
    // router.push/replace 的路径不含 basePath（Next 自动前置 /skills）
    router.replace(`/?${p.toString()}`, { scroll: false });
  }

  const [skills, setSkills] = useState<SkillCard[]>([]);
  const [exportTargets, setExportTargets] = useState<ExportTarget[]>([]);
  const [targetsError, setTargetsError] = useState('');
  const [targetsLoading, setTargetsLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [checkingUpdates, setCheckingUpdates] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const [pendingUnpublish, setPendingUnpublish] = useState<PendingUnpublish | null>(null);
  const [pendingClone, setPendingClone] = useState<PendingClone | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [registerRepository, setRegisterRepository] = useState('');
  const [activeTask, setActiveTask] = useState<ActiveGithubTask | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const refreshTargets = useCallback(async () => {
    setTargetsLoading(true);
    try {
      setExportTargets((await listExportTargets()).items);
      setTargetsError('');
    } catch (err) {
      setTargetsError(err instanceof Error ? err.message : '加载导出目标失败');
    } finally { setTargetsLoading(false); }
  }, []);

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
    void refreshTargets();
  }, [refreshSkills, refreshTargets]);

  const refreshAll = useCallback(async () => { await Promise.all([refreshSkills(), refreshTargets()]); }, [refreshSkills, refreshTargets]);

  const localSkills = useMemo(
    () => skills.filter((skill) => skill.source === 'local'),
    [skills]
  );
  const githubSkills = useMemo(
    () => skills.filter((skill) => skill.source === 'github'),
    [skills]
  );

  async function handleCheckUpdates(skillIds: string[] = []) {
    if (checkingUpdates) return;
    setCheckingUpdates(true);
    setNotice(null);
    try {
      const response = await checkUpdates(skillIds);
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
        kind: response.items.some(i => i.result !== 'ok') ? 'err' : 'ok',
        text: `检查完成：${updatable.length} 个 Skill 有远端更新${response.items.some(i => i.result !== 'ok') ? `；检查失败：${response.items.filter(i => i.result !== 'ok').map(i => `${i.skill_id}：${i.error}`).join('；')}` : ''}`,
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

  async function performUnpublish(password: string) {
    if (!pendingUnpublish || pendingUnpublish.items.length === 0 || actionBusy) return;
    setActionBusy(true);
    setActionError('');
    try {
      const results = await runUnpublishBatch(pendingUnpublish.items, item => unpublishSkill(item.skillId, item.target, password));
      const failed = results.filter(item => item.status === 'error');
      setPendingUnpublish(prev => prev ? { ...prev, items: failed,
        results: [...prev.results.filter(old => !results.some(item => item.skillId === old.skillId && item.target === old.target)), ...results] } : null);
      if (failed.length > 0) setActionError(`${failed.length} 项失败，重新确认仅重试失败项`);
      setNotice({ kind: failed.length ? 'err' : 'ok', text: `下架完成：${results.length - failed.length} 项成功，${failed.length} 项失败` });
      await refreshAll();
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
    const { skillId, skillName } = pendingClone;
    try {
      // 同步段只做密码/预检校验；clone 在后台任务执行（PRD R3）
      const created = await cloneGithubCache(skillId, password);
      setPendingClone(null);
      setActiveTask({
        taskId: created.task_id,
        title: `Clone 缓存「${skillName}」`,
        successNotice: `「${skillName}」缓存已就绪`,
      });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Clone 失败');
    } finally {
      setActionBusy(false);
    }
  }

  async function performDelete(password: string) {
    if (!pendingDelete) {
      return;
    }
    setActionBusy(true);
    setActionError('');
    try {
      await deleteSkill(pendingDelete.skillId, password);
      setPendingDelete(null);
      setNotice({ kind: 'ok', text: `已删除 GitHub Skill「${pendingDelete.skillName}」` });
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <main className="mx-auto flex h-screen max-w-7xl flex-col gap-3 p-4">
      <header className="flex items-center justify-between gap-3 border-b border-slate-100 pb-1">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-1">
          <div className="flex flex-col gap-0.5">
            {/* 站点首页在 basePath 之外，Next Link 会将 / 拼成 /skills。 */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a href="/" className="text-xs text-slate-500 transition-colors hover:text-slate-800">
              ← 返回首页
            </a>
            <h1 className="text-xl font-semibold text-slate-800">Skill 发布管理台</h1>
          </div>
          <nav className="flex gap-1" aria-label="视图切换">
            <button
              type="button"
              data-active={view === 'manage'}
              onClick={() => navigate({ view: 'manage' })}
              className="border-b-2 border-transparent px-3 pb-2 pt-2.5 text-sm text-slate-500 hover:text-slate-800 data-[active=true]:border-sky-600 data-[active=true]:font-medium data-[active=true]:text-slate-800"
            >
              管理看板
            </button>
            <button
              type="button"
              data-active={view === 'board'}
              onClick={() => navigate({ view: 'board' })}
              className="border-b-2 border-transparent px-3 pb-2 pt-2.5 text-sm text-slate-500 hover:text-slate-800 data-[active=true]:border-sky-600 data-[active=true]:font-medium data-[active=true]:text-slate-800"
            >
              部署看板
            </button>
            <button type="button" data-active={view === 'targets'} onClick={() => navigate({ view: 'targets' })} className="border-b-2 border-transparent px-3 pb-2 pt-2.5 text-sm text-slate-500 hover:text-slate-800 data-[active=true]:border-sky-600 data-[active=true]:font-medium data-[active=true]:text-slate-800">导出目标</button>
          </nav>
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

      <div className={view === 'targets' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}><ExportTargetManager targets={exportTargets} loading={targetsLoading} error={targetsError} onRefresh={refreshTargets} /></div>
      {view !== 'targets' && targetsError ? <p role="alert" className="rounded bg-rose-50 px-3 py-2 text-sm text-rose-700">{targetsError}<button type="button" onClick={() => void refreshTargets()} className="ml-3 underline">重试</button></p> : null}

      {/* 管理看板：来源子 segmented + 两个常驻挂载的来源工作区 */}
      <div
        className={
          view === 'manage'
            ? 'flex min-h-0 flex-1 flex-col gap-3'
            : 'hidden'
        }
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-0.5 rounded-md border border-slate-200 bg-slate-50 p-0.5">
            <button
              type="button"
              data-active={sourceTab === 'local'}
              onClick={() => navigate({ tab: 'local' })}
              className={SEG_BUTTON}
            >
              自研 Skill
              <span className="ml-1.5 rounded-full border border-slate-200 bg-slate-100 px-1.5 text-xs text-slate-500">
                {localSkills.length}
              </span>
            </button>
            <button
              type="button"
              data-active={sourceTab === 'github'}
              onClick={() => navigate({ tab: 'github' })}
              className={SEG_BUTTON}
            >
              GitHub Skill
              <span className="ml-1.5 rounded-full border border-slate-200 bg-slate-100 px-1.5 text-xs text-slate-500">
                {groupCollections(githubSkills).length}
              </span>
            </button>
          </div>
          <div className="flex items-center gap-2">
            {sourceTab === 'local' ? (
              <span className="text-xs italic text-slate-400">
                自研 Skill 由源库目录自动同步，无需登记
              </span>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => void handleCheckUpdates()}
                  disabled={checkingUpdates}
                  className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {checkingUpdates ? '检查中…' : '检查 GitHub 更新'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActionError('');
                    setRegisterRepository('');
                    setShowRegister(true);
                  }}
                  className="rounded bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-800"
                >
                  新增 GitHub Skill
                </button>
              </>
            )}
          </div>
        </div>

        <div className={sourceTab === 'local' ? 'flex min-h-0 flex-1' : 'hidden'}>
          <SourceWorkspace
            source="local"
            skills={localSkills}
            loading={loading}
            onRefresh={refreshAll}
            exportTargets={exportTargets}
            targetsError={targetsLoading ? '导出目标加载中…' : targetsError}
            onManageTargets={() => navigate({ view: 'targets' })}
            onNotify={setNotice}
            onClone={(skillId, skillName) => {
              setActionError('');
              setPendingClone({ skillId, skillName });
            }}
            onDelete={(skill) => {
              setActionError('');
              setPendingDelete({ skillId: skill.id, skillName: skill.name });
            }}
            onUnpublish={(skillId, skillName, targets) => {
              setActionError('');
              setPendingUnpublish({ name: skillName, items: targets.map(target => ({ skillId, skillName, target })), results: [] });
            }}
          />
        </div>
        <div className={sourceTab === 'github' ? 'flex min-h-0 flex-1' : 'hidden'}>
          <SourceWorkspace
            source="github"
            onAddMembers={(repository) => {
              setActionError('');
              setRegisterRepository(repository);
              setShowRegister(true);
            }}
            checkingUpdates={checkingUpdates}
            onCheckUpdates={handleCheckUpdates}
            skills={githubSkills}
            loading={loading}
            onRefresh={refreshAll}
            exportTargets={exportTargets}
            targetsError={targetsLoading ? '导出目标加载中…' : targetsError}
            onManageTargets={() => navigate({ view: 'targets' })}
            onNotify={setNotice}
            onClone={(skillId, skillName) => {
              setActionError('');
              setPendingClone({ skillId, skillName });
            }}
            onDelete={(skill) => {
              setActionError('');
              setPendingDelete({ skillId: skill.id, skillName: skill.name });
            }}
            onUnpublish={(skillId, skillName, targets) => {
              setActionError('');
              setPendingUnpublish({ name: skillName, items: targets.map(target => ({ skillId, skillName, target })), results: [] });
            }}
          />
        </div>
      </div>

      {/* 部署看板 */}
      <div className={view === 'board' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>
        <DeployBoard
          skills={skills}
          agent={agent}
          onAgentChange={(next) => navigate({ agent: next })}
          onUnpublishCollection={(name, members, target) => {
            setActionError('');
            setPendingUnpublish({ name, items: members.map(skill => ({ skillId: skill.id, skillName: skill.name, target })), results: [] });
          }}
          onUnpublish={(skillId, skillName, target) => {
            setActionError('');
            setPendingUnpublish({ name: skillName, items: [{ skillId, skillName, target }], results: [] });
          }}
        />
      </div>

      {pendingUnpublish ? (
        <ConfirmActionDialog
          title={pendingUnpublish.items.length ? '确认下架' : '下架结果'}
          description={
            <div className="space-y-2">
              <p>「{pendingUnpublish.name}」：待下架 {pendingUnpublish.items.length} 项，只移除所列 Agent 的技能链接。</p>
              <ul className="space-y-1 text-xs">{pendingUnpublish.items.map(item => <li key={`${item.skillId}-${item.target}`}>{item.skillName} → {TARGET_LABEL[item.target]}</li>)}</ul>
              {pendingUnpublish.results.length ? <ul className="space-y-1 text-xs">{pendingUnpublish.results.map(item => (
                <li key={`${item.skillId}-${item.target}`} className={item.status === 'error' ? 'text-rose-700' : 'text-emerald-700'}>
                  {item.skillName} → {TARGET_LABEL[item.target]}：{item.status === 'success' ? '成功' : item.error}
                </li>
              ))}</ul> : null}
            </div>
          }
          confirmLabel={pendingUnpublish.results.length ? '重试失败项' : '确认下架'}
          completed={pendingUnpublish.items.length === 0}
          busy={actionBusy}
          error={actionError}
          onConfirm={(password) => void performUnpublish(password)}
          onCancel={() => setPendingUnpublish(null)}
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

      {pendingDelete ? (
        <ConfirmActionDialog
          title="确认删除 Skill"
          description={
            <p>
              将移除「{pendingDelete.skillName}
              」的登记条目并删除本机缓存（不影响已发布目标；已有
              active 部署时需先下架）。此操作通过 Git 提交全局生效。
            </p>
          }
          confirmLabel="确认删除"
          busy={actionBusy}
          error={actionError}
          onConfirm={(password) => void performDelete(password)}
          onCancel={() => setPendingDelete(null)}
        />
      ) : null}

      {showRegister ? (
        <RegisterGithubDialog
          initialRepository={registerRepository}
          existingSkills={githubSkills}
          onRefresh={refreshAll}
          busy={actionBusy}
          error={actionError}
          onCancel={() => setShowRegister(false)}
        />
      ) : null}

      {activeTask ? (
        <TaskProgressDialog
          taskId={activeTask.taskId}
          title={activeTask.title}
          onDone={(task: TaskSnapshot) => {
            setActiveTask(null);
            if (task.results.length > 0) {
              // 批量登记：notice 按逐项成败统计（部分成功时提示 err 引导复查）
              const ok = task.results.filter((item) => item.status === 'success').length;
              setNotice({
                kind: ok === task.results.length ? 'ok' : 'err',
                text: `批量登记完成：${ok}/${task.results.length} 项成功`,
              });
            } else {
              setNotice({ kind: 'ok', text: activeTask.successNotice });
            }
            void refreshSkills();
          }}
          onClose={() => setActiveTask(null)}
        />
      ) : null}
    </main>
  );
}

/** useSearchParams 在静态渲染下要求 Suspense 边界（Next.js 15）。 */
export default function Page() {
  return (
    <Suspense fallback={<main className="p-6 text-sm text-slate-400">加载中…</main>}>
      <SkillManagerPage />
    </Suspense>
  );
}
