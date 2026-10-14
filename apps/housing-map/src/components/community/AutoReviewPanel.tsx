'use client';

import { useEffect, useRef, useState } from 'react';
import { AutoReviewEvidence, AutoReviewReport, labels, request } from './DirectoryCards';

type Status = { enabled: boolean; rule_version: string; last_report?: AutoReviewReport };
const actions: Record<string, string> = { admit: '建议收录', merge: '补充已有住宅', pending: '保留待审', exclude: '建议排除（人工确认）', protected: '保留已排除' };
const outcomes: Record<string, string> = { applied: '已执行', skipped: '保留人工处理', conflict: '资料冲突，未执行' };

export function AutoEvidence({ evidence }: { evidence: AutoReviewEvidence[] }) {
  return <>{evidence.map((e, i) => <p className="directory-muted" key={i}>{labels[e.source] || e.source} · {e.source_id} · {e.name} · {e.address} · {e.property_type || '未提供整小区用途'}{e.property_type_error && ` · ${e.property_type_error}`}</p>)}</>;
}

export function AutoReport({ report }: { report: AutoReviewReport }) {
  return <div className="auto-review-report"><p className="directory-muted">规则：{report.rule_version}{report.executed_at && ` · 执行时间：${report.executed_at}`}</p>
    <p>{Object.entries(report.counts).map(([key, value]) => `${actions[key] || outcomes[key] || key} ${value}`).join(' · ')}</p>
    <p className="directory-muted">建议排除仍需人工确认；预演结果不改变住宅名单和地图。</p>
    <details><summary>逐项结果与依据（{report.items.length} 个候选）</summary>{report.items.map(item => <article className="directory-source-card" key={item.candidate_id}>
      <strong>{item.name}</strong> · {actions[item.action]}{item.outcome && ` · ${outcomes[item.outcome]}`}
      <p>{item.reasons.join('；')}{item.error && `；${item.error}`}</p>
      <AutoEvidence evidence={item.evidence} />
    </article>)}</details>
  </div>;
}

export default function AutoReviewPanel({ onChanged, refreshVersion = 0 }: { onChanged: () => void; refreshVersion?: number }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [preview, setPreview] = useState<AutoReviewReport | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<'enable' | 'execute' | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const controller = new AbortController();
    request<Status>('/auto-review', 'GET', undefined, controller.signal).then(setStatus).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [refreshVersion]);
  useEffect(() => { if (confirm) dialog.current?.showModal(); }, [confirm]);
  async function act(action: 'preview' | 'enable' | 'disable' | 'execute') {
    setBusy(true); setError(''); setConfirm(null);
    try {
      if (action === 'preview') setPreview(await request<AutoReviewReport>('/auto-review/preview', 'POST'));
      else if (action === 'execute') {
        const result = await request<AutoReviewReport>('/auto-review/execute', 'POST', { snapshot_id: preview?.snapshot_id });
        setPreview(null); setStatus(s => s && ({ ...s, last_report: result })); onChanged();
      } else setStatus(await request<Status>('/auto-review/config', 'PUT', { enabled: action === 'enable', snapshot_id: action === 'enable' ? preview?.snapshot_id : undefined }));
    } catch (e) { setError(e instanceof Error ? e.message : '自动审核暂不可用'); if (action !== 'disable') setPreview(null); }
    finally { setBusy(false); }
  }
  return <details className="review-collection"><summary>自动审核 · {status?.enabled ? '已启用' : '默认仅预演'}</summary>
    <p>先预演并核对依据，再明确启用。收录需要住宅证据和可靠身份；人工锁始终优先。启用后，后续采集会自动处理符合规则的候选。</p>
    <p className="directory-muted">只读取已保存资料，不访问来源网站；预演不改变住宅名单。</p>
    <div className="directory-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => void act('preview')}>生成只读预演</button>
      {status?.enabled ? <button className="btn btn-secondary" disabled={busy} onClick={() => void act('disable')}>关闭自动审核</button> : <button className="btn btn-secondary" disabled={busy || !preview} onClick={() => setConfirm('enable')}>核对后明确启用</button>}
      <button className="btn btn-primary" disabled={busy || !status?.enabled || !preview} onClick={() => setConfirm('execute')}>执行当前预演</button></div>
    {error && <p role="alert" className="directory-warning">{error}</p>}
    {preview && <AutoReport report={preview} />}{status?.last_report && <details><summary>最近一次实际处理</summary><AutoReport report={status.last_report} /></details>}
    {confirm && <dialog ref={dialog} className="directory-confirm" aria-label="确认自动审核" onCancel={() => setConfirm(null)}>
      <p>{confirm === 'enable' ? '已核对预演依据，启用后续采集的自动收录和来源补充？建议排除仍留给人工；人工锁继续生效。' : '执行刚才核对的收录和来源补充建议？资料如有变化会要求重新预演。'}</p>
      <div className="directory-actions"><button className="btn btn-primary" disabled={busy} onClick={() => void act(confirm)}>确认{confirm === 'enable' ? '启用' : '执行'}</button><button className="btn btn-secondary" onClick={() => setConfirm(null)}>返回核对</button></div>
    </dialog>}
  </details>;
}
