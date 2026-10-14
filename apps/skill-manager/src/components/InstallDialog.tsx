'use client';
import { useEffect, useRef, useState } from 'react';
import { executeInstall, getInstallTask, previewInstall, type InstallInput, type InstallPlan, type InstallTask } from '@/lib/api';
import { useInstallTargets, installTargetLabel } from '@/lib/installTargets';
import ConfirmActionDialog from './ConfirmActionDialog';

export default function InstallDialog({input, onClose, onRefresh}: {input: InstallInput; onClose: () => void; onRefresh: () => Promise<void>}) {
  const refresh = useRef(onRefresh); refresh.current = onRefresh;
  const [generation, setGeneration] = useState(0);
  const {current, targets, error: targetsError, loading: targetsLoading} = useInstallTargets();
  const [chosenTargets, setChosenTargets] = useState<string[]>(input.target_ids ?? [current]);
  const initial = JSON.stringify(input);
  const label = (id: string) => installTargetLabel(targets, id);
  const [selection, setSelection] = useState(initial);
  const [plan, setPlan] = useState<InstallPlan>();
  const [task, setTask] = useState<InstallTask>();
  const [error, setError] = useState('');
  const [preparing, setPreparing] = useState(true);
  const [busy, setBusy] = useState(false);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const submitting = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setSelection(initial); }, [initial]);
  useEffect(() => {
    let valid = true;
    setPreparing(true); setError(''); setPlan(undefined); setTask(undefined); setRequestId(crypto.randomUUID());
    const selected: InstallInput = JSON.parse(selection);
    if (!selected.items) selected.target_ids = chosenTargets;
    if (!chosenTargets.length && !selected.items) { setError('请选择至少一个 profile'); setPreparing(false); return; }
    previewInstall(selected).then(result => { if (valid) setPlan(result); }).catch(e => { if(valid) setError(e.message); }).finally(() => { if(valid) setPreparing(false); });
    return () => { valid = false; };
  }, [selection, generation, chosenTargets]);
  const [taskId, setTaskId] = useState('');
  useEffect(() => {
    if (!taskId) return;
    let valid = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await getInstallTask(taskId);
        if (!valid) return;
        setTask(result);
        if (result.state === 'done') { setBusy(false); submitting.current = false; await refresh.current(); }
        else timer = setTimeout(poll, 1000);
      } catch (e) { if(valid) { setError(e instanceof Error ? e.message : '安装任务查询失败'); setBusy(false); submitting.current = false; } }
    };
    void poll();
    return () => { valid = false; clearTimeout(timer); };
  }, [taskId]);
  const confirm = async (password: string) => {
    if (!plan || submitting.current || preparing || targetsLoading || targetsError) return;
    submitting.current = true; setBusy(true); setError('');
    try { const result = await executeInstall(plan.plan_id, requestId, password); if(mounted.current) setTaskId(result.task_id); }
    catch (e) { if(mounted.current) { setError(e instanceof Error ? e.message : '安装失败'); setBusy(false); } submitting.current = false; }
  };
  const retry = () => {
    const failures = task?.results.filter(r => r.status !== 'success') ?? [];
    const original: InstallInput = JSON.parse(selection);
    const selected: InstallInput = original.candidates ? {
      scan_task_id: original.scan_task_id, shared_paths: original.shared_paths,
      candidates: original.candidates.flatMap(candidate => {
        const skillId = plan?.items.find(i => i.path === candidate.path)?.skill_id;
        const targets = failures.filter(r => r.skill_id === skillId).map(r => r.target);
        return targets.length ? [{...candidate, targets}] : [];
      }),
    } : {items: failures.map(r => ({skill_id: r.skill_id, targets: [r.target]}))};
    setChosenTargets([...new Set(failures.map(r => r.target))]);
    setTaskId(''); setTask(undefined); setSelection(JSON.stringify(selected)); setGeneration(g => g + 1);
  };
  const done = task?.state === 'done';
  const labels: Record<string, string> = {add:'新增', update:'更新', unchanged:'跳过', blocked:'无法安装'};
  return <ConfirmActionDialog title="安装到 Hermes profile" confirmLabel="确认安装" completed={!!targetsError || done || (!preparing && !!plan && !plan.items.some(i => i.action === 'add' || i.action === 'update'))} busy={busy || preparing || targetsLoading} error={error || targetsError}
    onConfirm={password => void confirm(password)} onCancel={onClose} description={<div className="space-y-2">
      <fieldset disabled={busy || targetsLoading || !!taskId} className="space-y-1">
        <legend>安装目标（共享同一份源内容）</legend>
        {chosenTargets.filter(id => !targets.some(t => t.id === id)).map(id => <label key={id} className="block text-amber-700">
          <input type="checkbox" checked onChange={() => { setPlan(undefined); setPreparing(true); setChosenTargets(prev => prev.filter(t => t !== id)); }} /> {id}（目标未配置，请取消选择）
        </label>)}
        {targets.map(target => <label key={target.id} className="block text-sm">
          <input type="checkbox" checked={chosenTargets.includes(target.id)} disabled={(!target.available && !chosenTargets.includes(target.id)) || !!JSON.parse(selection).items || !!JSON.parse(selection).candidates?.some((c: {targets?: string[]}) => c.targets)}
            onChange={e => { setTaskId(''); setPlan(undefined); setPreparing(true); setChosenTargets(prev => e.target.checked ? [...prev, target.id] : prev.filter(id => id !== target.id)); }} />
          {' '}{target.name} · {target.profile_name}
          <span className="block break-all text-xs text-slate-500">{target.install_path} {target.unavailable_reason}</span>
        </label>)}
      </fieldset>
      {preparing ? <p>正在准备安装计划…</p> : <p>新增 {plan?.items.filter(i => i.action === 'add').length ?? 0} · 更新 {plan?.items.filter(i => i.action === 'update').length ?? 0} · 跳过 {plan?.items.filter(i => i.action === 'unchanged').length ?? 0} · 无法安装 {plan?.items.filter(i => i.action === 'blocked').length ?? 0}</p>}
      {plan?.items.map(i => <p key={`${i.skill_id}:${i.target}`}>{i.name} → {label(i.target)}：{labels[i.action]} {i.planned_revision?.slice(0,7)} {i.reason}</p>)}
      {plan?.affected_installations?.map(item => <p key={`${item.skill_id}:${item.target}`} className="text-xs text-amber-700">共享更新影响：{item.name} → {label(item.target)}</p>)}
      {plan?.items.some(i => i.planned_revision) && <p className="text-xs text-slate-500">GitHub 仓库更新后，同仓库已安装的 Skill 会同步更新。</p>}
      {busy && task && <p role="status">{({preparing:'准备中', registering:'登记中', installing:'安装中'} as Record<string,string>)[task.stage] ?? task.stage} · 已处理 {task.results.length}/{plan?.items.length}</p>}
      {task?.results.map(r => <p key={`${r.skill_id}:${r.target}`}>{r.name} → {label(r.target)}：{r.status === 'success' ? '安装成功' : `${r.registered ? '已登记、未安装' : '未安装'} — ${r.error}`}</p>)}
      {done && task.results.some(r => r.status !== 'success') && <button type="button" onClick={retry} className="text-sky-700 underline">仅重试失败项</button>}
      {!busy && error && <button type="button" onClick={() => { setTaskId(''); setGeneration(g => g + 1); }} className="text-sky-700 underline">重新预览</button>}
    </div>} />;
}
