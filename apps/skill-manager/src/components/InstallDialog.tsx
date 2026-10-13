'use client';
import { useEffect, useRef, useState } from 'react';
import { executeInstall, getInstallTask, previewInstall, type InstallInput, type InstallPlan, type InstallTask } from '@/lib/api';
import ConfirmActionDialog from './ConfirmActionDialog';

export default function InstallDialog({input, onClose, onRefresh}: {input: InstallInput; onClose: () => void; onRefresh: () => Promise<void>}) {
  const refresh = useRef(onRefresh); refresh.current = onRefresh;
  const [generation, setGeneration] = useState(0);
  const initial = JSON.stringify(input);
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
    previewInstall(JSON.parse(selection)).then(result => { if (valid) setPlan(result); }).catch(e => { if(valid) setError(e.message); }).finally(() => { if(valid) setPreparing(false); });
    return () => { valid = false; };
  }, [selection, generation]);
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
    if (!plan || submitting.current || preparing) return;
    submitting.current = true; setBusy(true); setError('');
    try { const result = await executeInstall(plan.plan_id, requestId, password); if(mounted.current) setTaskId(result.task_id); }
    catch (e) { if(mounted.current) { setError(e instanceof Error ? e.message : '安装失败'); setBusy(false); } submitting.current = false; }
  };
  const retry = () => {
    const failed = task?.results.filter(r => r.status !== 'success').map(r => r.skill_id) ?? [];
    const selected: InstallInput = JSON.parse(selection);
    if (selected.skill_ids) selected.skill_ids = selected.skill_ids.filter(id => failed.includes(id));
    else selected.candidates = selected.candidates?.filter(c => plan?.items.some(i => i.path === c.path && failed.includes(i.skill_id)));
    setTaskId(''); setTask(undefined); setSelection(JSON.stringify(selected)); setGeneration(g => g + 1);
  };
  const done = task?.state === 'done';
  const labels: Record<string, string> = {add:'新增', update:'更新', unchanged:'跳过', blocked:'无法安装'};
  return <ConfirmActionDialog title="安装到 Hermes" confirmLabel="确认安装" completed={done || (!preparing && !!plan && !plan.items.some(i => i.action === 'add' || i.action === 'update'))} busy={busy || preparing} error={error}
    onConfirm={password => void confirm(password)} onCancel={onClose} description={<div className="space-y-2">
      {preparing ? <p>正在准备安装计划…</p> : <p>新增 {plan?.items.filter(i => i.action === 'add').length ?? 0} · 更新 {plan?.items.filter(i => i.action === 'update').length ?? 0} · 跳过 {plan?.items.filter(i => i.action === 'unchanged').length ?? 0} · 无法安装 {plan?.items.filter(i => i.action === 'blocked').length ?? 0}</p>}
      {plan?.items.map(i => <p key={i.skill_id}>{i.name}：{labels[i.action]} {i.planned_revision?.slice(0,7)} {i.reason}</p>)}
      {busy && task && <p role="status">{({preparing:'准备中', registering:'登记中', installing:'安装中'} as Record<string,string>)[task.stage] ?? task.stage} · 已处理 {task.results.length}/{plan?.items.length}</p>}
      {task?.results.map(r => <p key={r.skill_id}>{r.name}：{r.status === 'success' ? '安装成功' : `${r.registered ? '已登记、未安装' : '未安装'} — ${r.error}`}</p>)}
      {done && task.results.some(r => r.status !== 'success') && <button type="button" onClick={retry} className="text-sky-700 underline">仅重试失败项</button>}
      {!busy && error && <button type="button" onClick={() => { setTaskId(''); setGeneration(g => g + 1); }} className="text-sky-700 underline">重新预览</button>}
    </div>} />;
}
