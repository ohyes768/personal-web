'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import ConfirmActionDialog from '@/components/ConfirmActionDialog';
import DeployBoard from '@/components/DeployBoard';
import ExportTargetManager from '@/components/ExportTargetManager';
import PackWorkspace from '@/components/PackWorkspace';
import SourceWorkspace, { type Notice } from '@/components/SourceWorkspace';

import { listGithubPacks, listSkills, listExportTargets, unpublishSkill } from '@/lib/api';
import type { TargetKey } from '@/lib/queue';
import type { ExportTarget, GithubPack, SkillCard } from '@/lib/types';

type ViewKey = 'manage' | 'board' | 'targets';
type SourceTab = 'local' | 'github';

import { TARGET_LABEL } from '@/lib/targets';

const SEG_BUTTON =
  'rounded px-3 py-1.5 text-sm transition-colors data-[active=true]:bg-white data-[active=true]:font-medium data-[active=true]:text-slate-800 data-[active=true]:shadow-sm text-slate-500 hover:text-slate-700';

interface PendingUnpublish {
  skillId: string;
  skillName: string;
  /** 待下架的 targets；每成功一个即移除，重试只针对剩余项 */
  targets: TargetKey[];
}

function SkillManagerPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // 两级导航：URL 是唯一真源，非法值在派生时逐级回退
  const view: ViewKey = searchParams.get('view') === 'board' ? 'board' : searchParams.get('view') === 'targets' ? 'targets' : 'manage';
  const sourceTab: SourceTab = searchParams.get('tab') === 'github' ? 'github' : 'local';
  const agent: TargetKey = searchParams.get('agent') === 'openclaw' ? 'openclaw' : 'hermes';

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
  const [notice, setNotice] = useState<Notice | null>(null);
  const [packs, setPacks] = useState<GithubPack[]>([]);
  const [packsLoading, setPacksLoading] = useState(true);
  const [packsError, setPacksError] = useState('');
  const [pendingUnpublish, setPendingUnpublish] = useState<PendingUnpublish | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const refreshPacks = useCallback(async () => {
    setPacksLoading(true);
    try { setPacks((await listGithubPacks()).items); setPacksError(''); }
    catch (err) { setPacksError(err instanceof Error ? err.message : '加载仓库包失败'); }
    finally { setPacksLoading(false); }
  }, []);
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
    void refreshPacks();
  }, [refreshSkills, refreshTargets, refreshPacks]);

  const refreshAll = useCallback(async () => { await Promise.all([refreshSkills(), refreshTargets(), refreshPacks()]); }, [refreshSkills, refreshTargets, refreshPacks]);

  const localSkills = useMemo(
    () => skills.filter((skill) => skill.source === 'local'),
    [skills]
  );
  async function performUnpublish(password: string) {
    if (!pendingUnpublish || pendingUnpublish.targets.length === 0) {
      return;
    }
    setActionBusy(true);
    setActionError('');
    const { skillId, skillName, targets } = pendingUnpublish;
    try {
      for (const target of targets) {
        await unpublishSkill(skillId, target, password);
        setPendingUnpublish((prev) =>
          prev ? { ...prev, targets: prev.targets.filter((t) => t !== target) } : prev
        );
      }
      setPendingUnpublish(null);
      setNotice({
        kind: 'ok',
        text: `${skillName} 已下架（${targets.map((t) => TARGET_LABEL[t]).join('、')}）`,
      });
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '操作失败');
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
              GitHub 仓库包
              <span className="ml-1.5 rounded-full border border-slate-200 bg-slate-100 px-1.5 text-xs text-slate-500">
                {packs.length}
              </span>
            </button>
          </div>
          <div className="flex items-center gap-2">
            {sourceTab === 'local' ? (
              <span className="text-xs italic text-slate-400">
                自研 Skill 由源库目录自动同步，无需登记
              </span>
            ) : (
              <span className="text-xs text-slate-400">按仓库整包添加、安装和更新</span>
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
            onClone={() => {}}
            onDelete={() => {}}
            onUnpublish={(skillId, skillName, targets) => {
              setActionError('');
              setPendingUnpublish({ skillId, skillName, targets });
            }}
          />
        </div>
        <div className={sourceTab === 'github' ? 'flex min-h-0 flex-1' : 'hidden'}>
          <PackWorkspace packs={packs} loading={packsLoading} error={packsError} onRefresh={refreshPacks} />
        </div>
      </div>

      {/* 部署看板 */}
      <div className={view === 'board' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>
        <DeployBoard
          skills={localSkills}
          agent={agent}
          onAgentChange={(next) => navigate({ agent: next })}
          onUnpublish={(skillId, skillName, target) => {
            setActionError('');
            setPendingUnpublish({ skillId, skillName, targets: [target] });
          }}
        />
        <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-slate-200 pt-3"><PackWorkspace packs={packs} loading={packsLoading} error={packsError} onRefresh={refreshPacks} agent={agent} /></div>
      </div>

      {pendingUnpublish ? (
        <ConfirmActionDialog
          title="确认下架"
          description={
            <p>
              将从 {pendingUnpublish.targets.map((t) => TARGET_LABEL[t]).join('、')} 移除「
              {pendingUnpublish.skillName}」的技能链接（不删除任何目录）。
            </p>
          }
          confirmLabel="确认下架"
          busy={actionBusy}
          error={actionError}
          onConfirm={(password) => void performUnpublish(password)}
          onCancel={() => setPendingUnpublish(null)}
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
