'use client';

import { useRef, useState } from 'react';
import ConfirmActionDialog from './ConfirmActionDialog';
import TaskProgressDialog from './TaskProgressDialog';
import { addGithubPack, checkGithubPack, deleteGithubPack, getGithubPackTask, installGithubPack, planGithubPack, uninstallGithubPack, updateGithubPack } from '@/lib/api';
import { packTargetLabel } from '@/lib/packs';
import { TARGET_LABEL, type LinkTargetKey } from '@/lib/targets';
import type { GithubPack, PackPlan } from '@/lib/types';

const TARGET_ORDER: LinkTargetKey[] = ['hermes', 'openclaw'];
const BUTTON = 'rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50';
type Action = { kind: 'add' } | { kind: 'update' | 'delete'; pack: GithubPack } | { kind: 'uninstall'; pack: GithubPack; target: LinkTargetKey } | { kind: 'install'; pack: GithubPack; targets: LinkTargetKey[]; plan: PackPlan };
interface Props {
  packs: GithubPack[];
  loading: boolean;
  error: string;
  onRefresh: () => Promise<void>;
  agent?: LinkTargetKey;
}

export default function PackWorkspace({ packs, loading, error, onRefresh, agent }: Props) {
  const [query, setQuery] = useState('');
  const [selectedTargets, setSelectedTargets] = useState<LinkTargetKey[]>(['hermes']);
  const [action, setAction] = useState<Action | null>(null);
  const [repository, setRepository] = useState('');
  const [name, setName] = useState('');
  const [summary, setSummary] = useState('');
  const [tags, setTags] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [activeTask, setActiveTask] = useState<{ id: string; title: string } | null>(null);

  function open(next: Action) { setActionError(''); setAction(next); }
  async function readAction(run: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setNotice('');
    try { await run(); } catch (err) { setNotice(err instanceof Error ? err.message : '请求失败'); }
    finally { busyRef.current = false; setBusy(false); }
  }
  async function perform(password: string) {
    if (!action || busyRef.current) return;
    busyRef.current = true; setBusy(true); setActionError('');
    try {
      let created;
      switch (action.kind) {
        case 'add':
          if (!repository.trim()) throw new Error('请输入 GitHub 仓库 URL');
          created = await addGithubPack({ repository: repository.trim(), ...(name.trim() ? { name: name.trim() } : {}), summary: summary.trim(), tags: tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean) }, password);
          break;
        case 'update': created = await updateGithubPack(action.pack.id, password); break;
        case 'install': created = await installGithubPack(action.pack.id, action.targets, password); break;
        case 'uninstall': await uninstallGithubPack(action.pack.id, action.target, password); break;
        case 'delete': await deleteGithubPack(action.pack.id, password); break;
      }
      setAction(null);
      if (created) setActiveTask({ id: created.task_id, title: action.kind === 'add' ? '添加仓库包' : action.kind === 'update' ? '更新仓库' : '安装仓库包' });
      else { setNotice('操作完成'); await onRefresh(); }
    } catch (err) { setActionError(err instanceof Error ? err.message : '操作失败'); }
    finally { busyRef.current = false; setBusy(false); }
  }
  const shown = packs.filter((pack) => (!agent || ['active', 'legacy_pending'].includes(pack.deployments[agent]?.status ?? '')) && `${pack.name} ${pack.repository} ${pack.tags.join(' ')}`.toLowerCase().includes(query.trim().toLowerCase()));
  const title = action?.kind === 'add' ? '添加 GitHub 仓库包' : action?.kind === 'update' ? '更新仓库' : action?.kind === 'install' ? '确认整包安装 / 转换' : action?.kind === 'uninstall' ? '卸载仓库包' : '删除仓库包';
  return <section className="flex min-h-0 flex-1 flex-col gap-3" aria-label={agent ? 'GitHub 仓库包部署' : 'GitHub 仓库包管理'}>
    <div className="flex flex-wrap items-center gap-2">
      <h2 className="text-sm font-medium text-slate-700">GitHub 仓库包 · {shown.length}</h2>
      <input aria-label="搜索仓库包" type="search" className="min-w-40 flex-1 rounded border border-slate-300 px-3 py-1.5 text-sm" placeholder="名称 / 来源 / 标签" value={query} onChange={(event) => setQuery(event.target.value)} />
      <button className={BUTTON} disabled={busy || loading} onClick={() => void onRefresh()}>刷新</button>
      {!agent ? <button className={BUTTON} disabled={busy} onClick={() => { setRepository(''); setName(''); setSummary(''); setTags(''); open({ kind: 'add' }); }}>添加仓库包</button> : null}
    </div>
    {error ? <p role="alert" className="text-sm text-rose-700">{error}<button className="ml-2 underline" onClick={() => void onRefresh()}>重试</button></p> : null}
    {notice ? <p role="status" className="rounded bg-slate-50 p-2 text-sm">{notice}</p> : null}
    {loading ? <p className="text-sm text-slate-500">加载仓库包…</p> : !shown.length ? <p className="rounded border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">暂无符合条件的仓库包</p> : null}
    <ul className="grid min-h-0 content-start gap-3 overflow-y-auto md:grid-cols-2 lg:grid-cols-3">
      {shown.map((pack) => <li key={pack.id} className="rounded-lg border border-slate-200 bg-white p-3">
        <h3 className="font-medium text-slate-800">{pack.name}</h3>
        <p className="break-all text-xs text-slate-500">{pack.repository}</p>
        <p className="mt-2 text-sm text-slate-600">{pack.skill_count} 个技能 · {pack.summary}</p>
        <div className="mt-1 flex flex-wrap gap-1">{pack.tags.map((tag) => <span key={tag} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{tag}</span>)}</div>
        {pack.has_update ? <p className="mt-2 text-xs text-amber-700">仓库有更新</p> : null}
        <div className="my-2 space-y-1 border-t border-slate-100 pt-2 text-xs">
          {(agent ? [agent] : TARGET_ORDER).map((target) => <div key={target}><span>{TARGET_LABEL[target]} · {packTargetLabel(pack, target)}</span>{pack.deployments[target]?.diagnostic ? <p className="text-amber-700">{pack.deployments[target]?.diagnostic}</p> : null}</div>)}
        </div>
        <details className="my-2 text-xs text-slate-600"><summary className="cursor-pointer">只读详情 · 技能清单与诊断</summary>
          <p className="my-2 break-all">跟踪分支：{pack.tracking_branch || '未知'} · 当前提交：{pack.current_revision || '未知'}</p>
          {pack.diagnostics.map((diagnostic, index) => <p key={index} className="text-amber-700">{diagnostic}</p>)}
          {TARGET_ORDER.map((target) => pack.deployments[target]?.link_target ? <p className="break-all" key={target}>{TARGET_LABEL[target]} → {pack.deployments[target]?.link_target}</p> : null)}
          <ul className="mt-2 max-h-60 space-y-2 overflow-y-auto">{pack.inventory.map((skill) => <li key={skill.path}><strong>{skill.name}</strong><p className="break-all">{skill.path}</p><p>{skill.description}</p></li>)}</ul>
        </details>
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-2">
          {!agent ? <>
            <button className={BUTTON} disabled={busy} onClick={() => readAction(async () => { const checked = await checkGithubPack(pack.id); await onRefresh(); setNotice(checked.has_update ? `${pack.name} 有远端更新` : `${pack.name} 已是最新`); })}>检查更新</button>
            <button className={BUTTON} disabled={busy} onClick={() => open({ kind: 'update', pack })}>{pack.source_missing ? '修复缓存' : '更新仓库'}</button>
            <button className={BUTTON} disabled={busy} onClick={() => open({ kind: 'delete', pack })}>删除</button>
          </> : null}
          <div className="flex w-full flex-wrap items-center gap-2">
            {!agent ? TARGET_ORDER.map((target) => <label key={target} className="text-xs text-slate-600"><input type="checkbox" checked={selectedTargets.includes(target)} onChange={(event) => setSelectedTargets((prev) => event.target.checked ? [...prev, target] : prev.filter((value) => value !== target))} /> {TARGET_LABEL[target]}</label>) : null}
            <button className={BUTTON} disabled={busy || (!agent && !selectedTargets.length)} onClick={() => readAction(async () => { const targets = agent ? [agent] : [...selectedTargets]; const plan = await planGithubPack(pack.id, targets); open({ kind: 'install', pack, targets, plan }); })}>预览安装 / 转换</button>
            {(agent ? [agent] : TARGET_ORDER).filter((target) => ['active', 'legacy_pending'].includes(pack.deployments[target]?.status ?? '')).map((target) => <button key={target} className={BUTTON} disabled={busy} onClick={() => open({ kind: 'uninstall', pack, target })}>卸载 {TARGET_LABEL[target]}</button>)}
          </div>
        </div>
      </li>)}
    </ul>
    {action ? <ConfirmActionDialog key={title} title={title} busy={busy} confirmDisabled={action.kind === 'install' && action.plan.items.some((item) => item.action === 'blocked')} error={actionError} confirmLabel={action.kind === 'add' ? '添加整包' : '确认执行'} onConfirm={(password) => perform(password)} onCancel={() => setAction(null)} description={action.kind === 'add' ? <div className="space-y-2">
      <p>添加整个仓库，系统自动发现技能。添加后另选目标安装。</p>
      <label className="block">GitHub 仓库 URL<input type="url" value={repository} onChange={(event) => setRepository(event.target.value)} className="mt-1 w-full rounded border p-2" placeholder="https://github.com/owner/repo" /></label>
      <label className="block">名称（可选）<input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 w-full rounded border p-2" /></label>
      <label className="block">标签（逗号分隔）<input value={tags} onChange={(event) => setTags(event.target.value)} className="mt-1 w-full rounded border p-2" /></label>
      <label className="block">简介<input value={summary} onChange={(event) => setSummary(event.target.value)} className="mt-1 w-full rounded border p-2" /></label>
    </div> : action.kind === 'update' ? <p>更新「{action.pack.name}」同时影响已安装此包的全部目标，无需再次发布。运行中读取可能与文件更新交错。缓存缺失时重新准备整个仓库。</p> : action.kind === 'install' ? <div><p>安装全部 {action.pack.skill_count} 个技能；旧部分安装转换后统一读取当前仓库。</p>{action.plan.items.map((item) => <p className={item.action === 'blocked' ? 'text-rose-700' : ''} key={item.target}>{TARGET_LABEL[item.target]} · {item.action} · {item.message}{item.legacy_skill_ids.length ? `（旧登记：${item.legacy_skill_ids.join('、')}）` : ''}</p>)}</div> : action.kind === 'uninstall' ? <p>从 {TARGET_LABEL[action.target]} 移除「{action.pack.name}」的受控安装链接，另一目标保持可用。</p> : <p>删除「{action.pack.name}」的包登记及无引用仓库。有现有安装引用时需先卸载。</p>} /> : null}
    {activeTask ? <TaskProgressDialog key={activeTask.id} taskId={activeTask.id} title={activeTask.title} fetchTask={getGithubPackTask} onClose={() => { setActiveTask(null); void onRefresh(); }} onDone={(task) => { setActiveTask(null); setNotice(task.result?.items?.some((item) => item.status !== 'success') ? '部分目标未完成，请检查诊断后重试' : '仓库包任务完成'); void onRefresh(); }} /> : null}
  </section>;
}


