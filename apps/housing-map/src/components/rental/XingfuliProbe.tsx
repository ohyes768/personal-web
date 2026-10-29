'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  PROBE_STAGES,
  probeIsRunning,
  probePath,
  probeRequest,
  probeStageLabel,
  type ProbeCandidate,
  type ProbeState,
} from '../../lib/rental-probe';
import { rentalDataChanged } from '../../lib/rental-sources';

const POLL_INTERVAL_MS = 2000;

function evidenceLine(candidate: ProbeCandidate) {
  if (candidate.conflicts.length) return candidate.conflicts.join('；');
  if (candidate.evidence.length) return candidate.evidence.join('；');
  return '平台未给出可核对的证据';
}

/** 一个候选主页：只展示平台事实与证据，不让用户处理平台 ID。 */
export function ProbeCandidateCard({ candidate, busy, onSelect }: {
  candidate: ProbeCandidate;
  busy: boolean;
  onSelect: () => void;
}) {
  return <article className="rental-source-candidate">
    <strong>{candidate.name}</strong>
    <p>平台地址：{candidate.address || '未记录'}{candidate.phase ? ` · ${candidate.phase}` : ''}</p>
    <p className="rental-meta">
      位置：{candidate.longitude != null && candidate.latitude != null
        ? `${candidate.longitude.toFixed(5)}, ${candidate.latitude.toFixed(5)}` : '平台未提供'}
    </p>
    <p className="rental-meta">证据：{evidenceLine(candidate)}</p>
    {candidate.evidence_gaps.length > 0 && <p className="rental-meta">待核实：{candidate.evidence_gaps.join('；')}</p>}
    <div className="rental-source-actions">
      <button className="btn btn-primary" disabled={busy || candidate.conflicts.length > 0} onClick={onSelect}>
        选择这个主页
      </button>
    </div>
  </article>;
}

/** 探查幸福里来源：点按钮、选主页，系统自己找租房入口。 */
export function XingfuliProbe({ communityId, onChanged }: {
  communityId: string;
  onChanged?: () => void;
}) {
  const [state, setState] = useState<{ id: string; data?: ProbeState; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const activeId = useRef(communityId);

  useEffect(() => {
    activeId.current = communityId;
    return () => { activeId.current = ''; };
  }, [communityId]);

  const load = useCallback(async () => {
    const data = await probeRequest<ProbeState>(probePath(communityId));
    if (activeId.current !== communityId) return null;
    setState({ id: communityId, data });
    return data;
  }, [communityId]);

  useEffect(() => {
    const controller = new AbortController();
    probeRequest<ProbeState>(probePath(communityId), { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ id: communityId, data }); })
      .catch(problem => {
        if (!controller.signal.aborted) setState({ id: communityId, error: problem.message });
      });
    return () => controller.abort();
  }, [communityId]);

  const current = state && state.id === communityId ? state : null;
  const data = current?.data;
  const loadError = current?.error;
  const stage = data?.stage;
  const stageLabel = probeStageLabel(stage);
  const message = data?.message?.trim();
  const running = probeIsRunning(stage);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => { void load().catch(() => undefined); }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [running, load]);

  async function act(suffix: string, body?: object) {
    setBusy(true);
    setActionError('');
    try {
      const next = await probeRequest<ProbeState>(probePath(communityId) + suffix, {
        method: 'POST',
        ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      });
      if (activeId.current !== communityId) return;
      setState({ id: communityId, data: next });
      if (next.stage === PROBE_STAGES.bound_pending_collection) {
        rentalDataChanged();
        onChanged?.();
      }
    } catch (problem) {
      if (activeId.current === communityId) {
        setActionError(problem instanceof Error ? problem.message : '操作失败，请重试');
      }
    } finally {
      // The busy flag must not survive a community switch, otherwise every
      // button of the new community stays disabled.
      setBusy(false);
    }
  }

  function selectCandidate(candidate: ProbeCandidate) {
    void act('/select', { candidate_id: candidate.candidate_id, revision: data?.revision ?? 0 });
  }

  const candidates = data?.candidates ?? [];
  const retryable = ['needs_homepage_selection', 'homepage_not_found', 'entry_not_found',
    'upstream_failed', 'cooling_down', 'deferred', 'cancelled', 'interrupted'];

  return <section className="rental-source-association" aria-label="探查幸福里来源">
    <h3>幸福里来源</h3>
    {loadError && <p role="alert">{loadError}</p>}
    {actionError && <p role="alert">{actionError}</p>}
    {!current && !loadError && <p role="status">正在加载探查状态…</p>}
    {current && <>
      <p role="status" className="rental-meta">
        {stageLabel}{message && message !== stageLabel ? ` · ${message}` : ''}
      </p>
      {stage === PROBE_STAGES.idle && <div className="rental-source-actions">
        <button className="btn btn-primary" disabled={busy} onClick={() => void act('')}>
          {busy ? '处理中…' : '探查幸福里来源'}
        </button>
      </div>}
      {running && <div className="rental-source-actions">
        <button className="btn btn-secondary" disabled={busy} onClick={() => void act('/cancel')}>取消探查</button>
      </div>}
      {candidates.length > 0 && <div role="group" aria-label="选择幸福里小区主页">
        {candidates.map(candidate => <ProbeCandidateCard key={candidate.candidate_id} candidate={candidate}
          busy={busy} onSelect={() => selectCandidate(candidate)} />)}
      </div>}
      {data?.selected_page && <p className="rental-meta">已选主页：{data.selected_page.name}</p>}
      {retryable.includes(stage ?? '') && <div className="rental-source-actions">
        <button className="btn btn-secondary" disabled={busy} onClick={() => void act('/retry')}>重试</button>
      </div>}
    </>}
  </section>;
}
