'use client';

import { useState } from 'react';
import { safeDirectoryLink } from './DirectoryCards';

export type UseReviewEvidence = { poi_id?: string; name?: string; typecode?: string; type_text?: string;
  address?: string; longitude?: number; latitude?: number; district?: string; matched_by?: string };
export type UseReviewHuman = { decision?: string; decided_at?: string; reason?: string;
  evidence?: { source?: string; url?: string; note?: string }[] };
export type UseReview = { state?: string; category?: string; result?: string; checked_at?: string; error?: string;
  evidence?: UseReviewEvidence | null; candidates_count?: number; human?: UseReviewHuman | null; re_review?: boolean;
  auto_skip_reason?: string | null };

export type UseReviewBucket = 'review' | 'done' | 'todo' | 'none' | 'skipped';

export const useReviewStateLabels: Record<string, string> = { checked: '已完成用途核对', not_found: '未找到高德地点',
  error: '查询失败', uncertain: '高德地点匹配不明确' };
export const useReviewResultLabels: Record<string, string> = { conflict: '用途冲突', uncertain: '用途待人工确认',
  agree_residential: '一致（住宅）', agree_non_residential: '一致（非住宅）', pending_retry: '未取得明确结果' };
export const useReviewBucketLabels: Record<UseReviewBucket, string> = { review: '待人工确认', done: '已一致',
  todo: '未取得明确结果', none: '尚未核对', skipped: '不自动核对' };
export const useReviewFilterLabels: Record<string, string> = { conflict: '用途冲突，待人工确认', uncertain: '用途待人工确认',
  agree: '用途一致', pending_retry: '未取得明确结果', none: '尚未核对', skipped: '不自动核对' };
export const useReviewSourceLabels: Record<string, string> = { kerui: '克而瑞', fang: '房天下', amap: '高德', other: '其他' };

// 旧任务和证据保存了提示原文；统一转换显示，无需重新查询高德。
const legacyUseReviewMessages: Record<string, string> = {
  '高德返回结果未完整，匹配不确定，待复核': '高德搜索结果未取完整，暂时无法确认匹配地点。',
  '高德候选用途不一致，匹配不确定，待复核': '高德候选地点的用途分类不一致或缺失，需人工核对。',
  '未找到名称与区域匹配的高德地点，待复核': '未找到名称与区域匹配的高德地点，可重新查询或补充小区别名。',
};
export function formatUseReviewMessage(message: string): string {
  return legacyUseReviewMessages[message] || message;
}

/** 高德分类只是第二来源证据：冲突与待确认都要人工看，其他情况不打扰。 */
export function useReviewBucket(review?: UseReview): UseReviewBucket {
  const result = review?.result;
  if (result === 'conflict' || result === 'uncertain') return 'review';
  if (result === 'agree_residential' || result === 'agree_non_residential') return 'done';
  if (review?.auto_skip_reason) return 'skipped';
  if (review?.state) return 'todo';
  return 'none';
}

export function UseReviewBadge({ review, compact = false }: { review?: UseReview; compact?: boolean }) {
  const bucket = useReviewBucket(review);
  const title = `${useReviewBucketLabels[bucket]} · ${review?.auto_skip_reason || useReviewResultLabels[review?.result || ''] || '尚未核对'}` +
    `${review?.re_review ? ' · 有新证据，待人工重新确认' : ''}${review?.checked_at ? ` · 最近核对 ${review.checked_at.slice(0, 10)}` : ''}`;
  if (compact) return <span className={`directory-badge directory-use-${bucket}`} title={title}>{useReviewBucketLabels[bucket]}</span>;
  return <><span className={`directory-badge directory-use-${bucket}`}>{useReviewBucketLabels[bucket]}</span>
    <small>{review?.auto_skip_reason || useReviewResultLabels[review?.result || ''] || '尚未核对'}</small>
    {review?.re_review && <small>有新证据，待人工重新确认</small>}</>;
}

export default function UseReviewPanel({ review, busy, revision, open, canConfirm = true, onToggle, onRecheck, onConfirm, pipeline = false }: {
  pipeline?: boolean;
  review?: UseReview; busy: boolean; revision?: number; open?: boolean; canConfirm?: boolean;
  onToggle?: (open: boolean) => void; onRecheck: () => void;
  onConfirm: (body: object) => void }) {
  const [decision, setDecision] = useState<'residential' | 'non_residential'>('residential');
  const [propertyType, setPropertyType] = useState('住宅');
  const [source, setSource] = useState('kerui');
  const [url, setUrl] = useState('');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const evidence = review?.evidence;
  const human = review?.human;
  const ready = !!url.trim() && (decision === 'residential' || !!reason.trim());
  const submit = () => {
    if (!ready) return;
    onConfirm({ revision, decision, property_type: decision === 'residential' ? propertyType : null,
      use_evidence: [{ source, url: url.trim(), note: note.trim() }], reason: reason.trim() });
  };
  return <section className="directory-use-review-panel" aria-label="住宅用途核对">
    <div className="directory-use-review-heading"><h4>住宅用途核对</h4><UseReviewBadge review={review} compact /></div>
    {pipeline && <p className="directory-muted">使用上方已确认地点的高德类型与透明售房网用途比较。确认位置后自动分类；有冲突再人工确认用途。</p>}
    {review?.auto_skip_reason && <p className="directory-muted">{review.auto_skip_reason}。仍可手动查询高德。</p>}
    {review?.re_review && <p role="alert" className="directory-warning">出现与人工结论相反的证据，请重新核对后再确认。</p>}
    <p className="directory-muted">{useReviewResultLabels[review?.result || ''] || '尚未核对'}
      {review?.checked_at ? ` · 最近核对 ${review.checked_at.slice(0, 10)}` : ''}</p>
    {evidence ? <p className="directory-source-summary-line">
      <span>高德地点：{evidence.name || '未命名'} · {evidence.type_text || evidence.typecode || '类型未知'}</span>
      {evidence.address && <span> · {evidence.address}</span>}
      {safeDirectoryLink(evidence.poi_id ? `https://www.amap.com/search?query=${encodeURIComponent(evidence.name || '')}` : '') &&
        <a href={`https://www.amap.com/search?query=${encodeURIComponent(evidence.name || '')}`} target="_blank" rel="noopener noreferrer">高德查看 ↗</a>}
    </p> : review?.state && <p className="directory-muted">{useReviewStateLabels[review.state] || '未取得明确结果'}</p>}
    {review?.error && <p role="status" className="directory-warning">{formatUseReviewMessage(review.error)}</p>}
    {human && <div className="directory-use-review-decision">
      <p>人工结论：{human.decision === 'residential' ? '确认住宅' : '确认非住宅'}{human.decided_at ? ` · ${human.decided_at.slice(0, 10)}` : ''}</p>
      {human.reason && <p>理由：{human.reason}</p>}
      {(human.evidence || []).map((item, i) => <p key={i}>{useReviewSourceLabels[item.source || ''] || item.source}
        {item.note ? ` · ${item.note}` : ''}
        {safeDirectoryLink(item.url || '') && <> · <a href={item.url} target="_blank" rel="noopener noreferrer">查看证据 ↗</a></>}</p>)}
    </div>}
    <div className="directory-actions">
      <button className="btn btn-secondary" disabled={busy} onClick={onRecheck}>{pipeline ? '核对已选主体类型' : '重新查询高德'}</button>
      {canConfirm && !open && <button className="btn btn-secondary" disabled={busy || !revision} onClick={() => onToggle?.(true)}>人工确认用途</button>}
    </div>
    {open && canConfirm && <div className="directory-use-review-confirm">
      <fieldset>
        <legend>人工确认用途</legend>
        <label><input type="radio" name="use-decision" checked={decision === 'residential'}
          onChange={() => setDecision('residential')} />确认是住宅</label>
        <label><input type="radio" name="use-decision" checked={decision === 'non_residential'}
          onChange={() => setDecision('non_residential')} />确认不是住宅</label>
      </fieldset>
      {decision === 'residential' && <label>住宅类型<select aria-label="住宅类型" value={propertyType} disabled={busy}
        onChange={e => setPropertyType(e.target.value)}>
        {['住宅', '别墅', '排屋'].map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>}
      <label>证据来源<select aria-label="证据来源" value={source} disabled={busy} onChange={e => setSource(e.target.value)}>
        {Object.entries(useReviewSourceLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>证据链接<input aria-label="证据链接" value={url} disabled={busy} maxLength={500}
        placeholder="如克而瑞、房天下或高德详情页链接" onChange={e => setUrl(e.target.value)} /></label>
      <label>证据说明<input aria-label="证据说明" value={note} disabled={busy} maxLength={300}
        placeholder="如：克而瑞标注为住宅" onChange={e => setNote(e.target.value)} /></label>
      <label>理由<textarea aria-label="确认理由" value={reason} disabled={busy} maxLength={300} rows={2}
        placeholder={decision === 'non_residential' ? '确认为非住宅必填' : '可选'} onChange={e => setReason(e.target.value)} /></label>
      <div className="directory-actions">
        <button className="btn btn-primary" disabled={busy || !ready} onClick={submit}>提交确认</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => onToggle?.(false)}>取消</button>
      </div>
      <p className="directory-muted">人工结论独立保存，采集刷新与重新查询都不会覆盖；出现相反证据时需人工重新确认。</p>
    </div>}
  </section>;
}
