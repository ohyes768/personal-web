/**
 * SessionDownloadButton — 下载某个 Hermes run 的会话记录（markdown）。
 * 供估值/评级报告弹窗共用；无 run_id（旧报告）不渲染。
 */
'use client';

import { useState } from 'react';
import { ApiHttpError } from '@/lib/api-client';

const buttonClass = 'text-xs text-accent hover:underline underline-offset-4 disabled:opacity-40 disabled:no-underline';

export function SessionDownloadButton({ runId, download }: {
  runId: string | null | undefined;
  download: (runId: string) => Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  if (!runId) return null;

  const handleClick = async () => {
    setPending(true);
    setError('');
    try {
      await download(runId);
    } catch (err) {
      setError(err instanceof ApiHttpError ? err.message : '下载失败，请重试');
    } finally {
      setPending(false);
    }
  };

  return (
    <span className="inline-flex items-center gap-1.5">
      <button type="button" className={buttonClass} disabled={pending} onClick={() => void handleClick()}>
        {pending ? '生成中…' : '下载会话记录'}
      </button>
      {error && <span role="alert" className="text-xs text-red-600">{error}</span>}
    </span>
  );
}
