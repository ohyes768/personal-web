'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BoundaryCandidate,
  BoundaryEstimateAccepted,
  BoundaryJob,
  BoundaryWorkflowState,
  BoundaryWorkflowError,
  boundaryErrorText,
  boundaryPaths,
  boundaryRequest,
  isBoundaryJobActive,
  newOperationId,
  runBoundaryAction,
} from './boundary-workflow';

const POLL_INTERVAL_MS = 2000;

interface BoundaryData {
  communityId: string;
  state: BoundaryWorkflowState | null;
  candidate: BoundaryCandidate | null;
  job: BoundaryJob | null;
}

interface BoundaryStatus {
  communityId: string;
  busy: boolean;
  error: string | null;
}

export interface BoundaryWorkflowView {
  state: BoundaryWorkflowState | null;
  job: BoundaryJob | null;
  candidate: BoundaryCandidate | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
  startEstimate: (options?: { regenerate?: boolean; refreshBuildings?: boolean }) => Promise<void>;
  applyCandidate: () => Promise<void>;
  rejectCandidate: () => Promise<void>;
  revert: () => Promise<void>;
  reload: () => Promise<void>;
}

/**
 * 单个小区轮廓工作流的状态与操作。
 *
 * 轮询只在前端进行:关闭弹框即停止轮询,服务端任务照常跑完;重新打开会重新读取状态并
 * 接着轮询。数据按小区 ID 存档,渲染时只取当前小区的快照 —— 切小区后迟到的响应不会把
 * 旧候选叠到新小区。
 */
export function useBoundaryWorkflow(
  communityId: string | null,
  onChanged?: () => void,
): BoundaryWorkflowView {
  const [data, setData] = useState<BoundaryData | null>(null);
  const [status, setStatus] = useState<BoundaryStatus>({ communityId: '', busy: false, error: null });
  const requestIdRef = useRef(0);
  const changedRef = useRef(onChanged);

  useEffect(() => {
    changedRef.current = onChanged;
  }, [onChanged]);

  const current = data && data.communityId === communityId ? data : null;
  const state = current?.state ?? null;
  const candidate = current?.candidate ?? null;
  const job = current?.job ?? null;
  const busy = status.communityId === communityId ? status.busy : false;
  const error = status.communityId === communityId ? status.error : null;
  const loading = !!communityId && !current;

  // 所有异步动作共用一条 busy 生命周期: 成功失败都会复位, 不会把按钮永久禁用
  const runAction = useCallback(async (communityId: string, action: () => Promise<void>, fallback?: string) => {
    await runBoundaryAction(action, {
      busy: () => setStatus({ communityId, busy: true, error: null }),
      settle: error => setStatus({ communityId, busy: false, error }),
    }, fallback);
  }, []);

  const patchData = useCallback((communityId: string, patch: Partial<BoundaryData>) => {
    setData(prev => {
      if (!prev || prev.communityId !== communityId) return prev;
      return { ...prev, ...patch };
    });
  }, []);

  const loadCandidate = useCallback(async (communityId: string, candidateId: string) => {
    const data = await boundaryRequest<BoundaryCandidate>(boundaryPaths.candidate(candidateId));
    patchData(communityId, { candidate: data });
  }, [patchData]);

  const reload = useCallback(async () => {
    if (!communityId) return;
    const requestId = ++requestIdRef.current;
    try {
      const state = await boundaryRequest<BoundaryWorkflowState>(boundaryPaths.workflow(communityId));
      if (requestIdRef.current !== requestId) return;
      setData(prev => ({
        communityId,
        state,
        candidate: prev?.communityId === communityId ? prev.candidate : null,
        job: prev?.communityId === communityId ? prev.job : null,
      }));
      if (state.candidate) await loadCandidate(communityId, state.candidate.candidate_id);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setStatus({ communityId, busy: false, error: err instanceof BoundaryWorkflowError ? err.message : '轮廓状态读取失败' });
    }
  }, [communityId, loadCandidate]);

  useEffect(() => {
    if (!communityId) return;
    const requestId = ++requestIdRef.current;
    let cancelled = false;
    (async () => {
      try {
        const state = await boundaryRequest<BoundaryWorkflowState>(boundaryPaths.workflow(communityId));
        if (cancelled || requestIdRef.current !== requestId) return;
        setData({ communityId, state, candidate: null, job: null });
        if (state.candidate) {
          const candidate = await boundaryRequest<BoundaryCandidate>(boundaryPaths.candidate(state.candidate.candidate_id));
          if (cancelled || requestIdRef.current !== requestId) return;
          setData(prev => prev?.communityId === communityId ? { ...prev, candidate } : prev);
        }
      } catch (err) {
        if (cancelled || requestIdRef.current !== requestId) return;
        setStatus({ communityId, busy: false, error: err instanceof BoundaryWorkflowError ? err.message : '轮廓状态读取失败' });
      }
    })();
    return () => { cancelled = true; };
  }, [communityId]);

  // 活动任务轮询:终态即停;关闭弹框(communityId 变 null)随之停止
  useEffect(() => {
    if (!communityId || !job || !isBoundaryJobActive(job.phase)) return;
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;

    const poll = async () => {
      try {
        const next = await boundaryRequest<BoundaryJob>(boundaryPaths.job(job.job_id));
        if (cancelled) return;
        patchData(communityId, { job: next });
        if (next.phase === 'succeeded' && next.candidate_id) {
          await loadCandidate(communityId, next.candidate_id);
          await reload();
          return;
        }
        if (next.phase === 'failed' || next.phase === 'interrupted') {
          setStatus({ communityId, busy: false, error: boundaryErrorText(next.error_code, next.error_message) });
          return;
        }
      } catch {
        // 网络抖动:下一轮继续
      }
      if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
    };

    timer = setTimeout(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [communityId, job, loadCandidate, patchData, reload]);

  const startEstimate = useCallback(async (options?: { regenerate?: boolean; refreshBuildings?: boolean }) => {
    if (!communityId) return;
    await runAction(communityId, async () => {
      const accepted = await boundaryRequest<BoundaryEstimateAccepted>(
        boundaryPaths.estimates(communityId),
        'POST',
        { regenerate: options?.regenerate ?? false, refresh_buildings: options?.refreshBuildings ?? false },
      );
      patchData(communityId, {
        job: {
          job_id: accepted.job_id,
          community_id: communityId,
          phase: accepted.phase,
          error_code: null,
          error_message: null,
          candidate_id: accepted.candidate_id ?? null,
          created_at: '',
          updated_at: '',
        },
      });
      if (accepted.candidate_id && !accepted.job_id) {
        await loadCandidate(communityId, accepted.candidate_id);
      }
      await reload();
    }, '生成失败,请稍后重试');
  }, [communityId, loadCandidate, patchData, reload, runAction]);

  const applyCandidate = useCallback(async () => {
    if (!communityId || !candidate) return;
    await runAction(communityId, async () => {
      await boundaryRequest(
        boundaryPaths.apply(candidate.candidate_id),
        'POST',
        { expected_revision: candidate.revision, operation_id: newOperationId() },
      );
      await reload();
      changedRef.current?.();
    }, '保存失败,请重试');
  }, [communityId, candidate, reload, runAction]);

  const rejectCandidate = useCallback(async () => {
    if (!communityId || !candidate) return;
    await runAction(communityId, async () => {
      await boundaryRequest(
        boundaryPaths.reject(candidate.candidate_id),
        'POST',
        { expected_revision: candidate.revision },
      );
      patchData(communityId, { candidate: null });
      await reload();
    }, '操作失败,请重试');
  }, [communityId, candidate, patchData, reload, runAction]);

  const revert = useCallback(async () => {
    const revertable = state?.revertable;
    if (!communityId || !revertable) return;
    await runAction(communityId, async () => {
      await boundaryRequest(
        boundaryPaths.revert(communityId),
        'POST',
        {
          expected_revision: state?.revision ?? '',
          apply_operation_id: revertable.operation_id,
          operation_id: newOperationId(),
        },
      );
      patchData(communityId, { candidate: null });
      await reload();
      changedRef.current?.();
    }, '撤销失败,请重试');
  }, [communityId, state, patchData, reload, runAction]);

  return {
    state,
    job,
    candidate,
    loading,
    busy,
    error,
    startEstimate,
    applyCandidate,
    rejectCandidate,
    revert,
    reload,
  };
}
