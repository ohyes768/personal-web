'use client';
import { useEffect, useState } from 'react';
export function CopyText({ text, disabled = false, label = '复制链接' }: { text: string; disabled?: boolean; label?: string }) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  useEffect(() => { setStatus('idle'); }, [text]);
  return <div className="min-w-0"><button disabled={disabled} onClick={async () => {
    try { await navigator.clipboard.writeText(text); setStatus('copied'); }
    catch { setStatus('failed'); }
  }} className="rounded-md border border-accent px-3 py-2 text-accent hover:bg-accent/10 disabled:opacity-40 whitespace-nowrap">{status === 'copied' ? '✓ 已复制' : label}</button>
    <span className="sr-only" role="status">{status === 'copied' ? '已复制' : ''}</span>
    {status === 'failed' && <div className="mt-2"><p role="alert" className="text-xs text-danger">自动复制失败，请选中下方内容手动复制。</p><textarea aria-label="手动复制内容" readOnly value={text} onFocus={e => e.currentTarget.select()} className="mt-1 w-full min-w-0 border border-rule rounded bg-paper-deep p-2 font-mono text-xs" /></div>}
  </div>;
}
