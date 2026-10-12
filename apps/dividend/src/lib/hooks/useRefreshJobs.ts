import { useCallback, useEffect, useRef, useState } from 'react';
import { dividendUpdateApi } from '../api';
import { ApiHttpError } from '../api-client';
import type { RefreshJob, RefreshKind } from '../types';

export const isRefreshActive = (job?: RefreshJob | null) => job?.status === 'queued' || job?.status === 'running';

export function useRefreshJobs(onComplete: (kind: RefreshKind) => void) {
  const [jobs, setJobs] = useState<Partial<Record<RefreshKind, RefreshJob>>>({});
  const [errors, setErrors] = useState<Partial<Record<RefreshKind, string>>>({});
  const [revision, setRevision] = useState(0);
  const current = useRef<Partial<Record<RefreshKind, RefreshJob>>>({});
  const complete = useRef(onComplete);
  complete.current = onComplete;
  const delivered = useRef(new Set<string>());
  const generations = useRef({ m120: 0, financial: 0 });

  const track = useCallback((job: RefreshJob) => {
    current.current[job.kind] = job;
    setJobs(prev => ({ ...prev, [job.kind]: job }));
    setErrors(prev => ({ ...prev, [job.kind]: undefined }));
    if (!isRefreshActive(job) && !delivered.current.has(job.job_id)) {
      delivered.current.add(job.job_id);
      complete.current(job.kind);
      setRevision(value => value + 1);
    }
  }, []);

  const accept = useCallback((job: RefreshJob) => {
    generations.current[job.kind]++;
    track(job);
  }, [track]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      await Promise.all((['m120', 'financial'] as const).map(async kind => {
        const generation = generations.current[kind];
        try {
          const active = current.current[kind];
          const job = isRefreshActive(active)
            ? await dividendUpdateApi.getRefreshJob(active!.job_id)
            : await dividendUpdateApi.getLatestRefreshJob(kind);
          if (!cancelled && generation === generations.current[kind]) {
            if (job?.job_id) track(job);
            setErrors(prev => ({ ...prev, [kind]: undefined }));
          }
        } catch (error) {
          if (!cancelled && generation === generations.current[kind]) {
            if (error instanceof ApiHttpError && error.status === 404) {
              // Rediscover the latest job next time; retain the missing-job message.
              delete current.current[kind];
              setJobs(prev => ({ ...prev, [kind]: undefined }));
            }
            setErrors(prev => ({ ...prev, [kind]: `暂时无法查询进度：${error instanceof Error ? error.message : '请稍后重试'}` }));
          }
        }
      }));
      if (!cancelled) timer = setTimeout(poll, document.hidden ? 10000 : 2000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [track]);

  return { jobs, errors, revision, accept };
}
