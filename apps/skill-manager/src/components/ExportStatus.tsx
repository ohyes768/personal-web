'use client';
import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import type { ExportTarget, SkillCard, TargetDeployment } from '@/lib/types';
import { exportTargetLabel, isInstallTarget, type ExportTargetKey } from '@/lib/targets';

interface Props {
  skill: SkillCard;
  targets: ExportTarget[];
  onExport: (skill: SkillCard, target: ExportTargetKey) => void;
  onDeleteExport: (skill: SkillCard, target: ExportTargetKey) => void;
}

function sourceStatus(skill: SkillCard, deployment: TargetDeployment) {
  if (skill.cache_missing || skill.source_missing) return '源不可用，无法核验';
  if (!deployment.content_hash) return '旧记录，无法核验';
  return deployment.stale ? '源已更新，建议重新导出' : '与当前源一致';
}

export default function ExportStatus({skill, targets, onExport, onDeleteExport}: Props) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState(false);
  const [position, setPosition] = useState<CSSProperties>({});
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const id = useId();
  const entries = Object.entries(skill.deployments).filter(([target, item]) => !isInstallTarget(target) && item.status === 'active');
  const staleCount = entries.filter(([, item]) => item.stale).length;
  const visible = (open || preview) && entries.length > 0;
  const sourceBlocked = skill.cache_missing || skill.source_missing;

  useEffect(() => {
    if (!visible || typeof document === 'undefined') return;
    const place = () => {
      const rect = trigger.current?.getBoundingClientRect();
      if (!rect) return;
      const above = rect.top > window.innerHeight / 2;
      const width = Math.min(360, window.innerWidth - 24);
      setPosition({
        width, left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
        ...(above ? {bottom: window.innerHeight - rect.top + 8} : {top: rect.bottom + 8}),
        maxHeight: Math.max(80, (above ? rect.top : window.innerHeight - rect.bottom) - 20),
      });
    };
    const dismiss = () => {setOpen(false); setPreview(false);};
    const outside = (event: Event) => {
      if (!trigger.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) dismiss();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      if (open) trigger.current?.focus();
      dismiss();
    };
    place();
    if (open) closeButton.current?.focus();
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    document.addEventListener('keydown', escape, true);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
      document.removeEventListener('keydown', escape, true);
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [visible, open]);

  if (!entries.length) return null;
  const close = () => {trigger.current?.focus(); setOpen(false); setPreview(false);};
  const actionClass = 'rounded-md px-2 py-1.5 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 disabled:cursor-not-allowed disabled:opacity-40';
  return <>
    <button ref={trigger} type="button" aria-label={`${skill.name} 导出记录`} aria-haspopup="dialog" aria-expanded={open}
      aria-controls={open ? id : undefined} aria-describedby={preview && !open ? id : undefined}
      onMouseEnter={() => setPreview(true)} onMouseLeave={() => setPreview(false)}
      onFocus={() => setPreview(true)} onBlur={() => setPreview(false)} onClick={() => {setOpen(!open); setPreview(false);}}
      className={`inline-flex h-6 shrink-0 items-center whitespace-nowrap rounded-full border px-2 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 ${staleCount ? 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100' : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'}`}>
      {staleCount ? `待更新 · ${staleCount}` : `已导出 · ${entries.length}`}
    </button>
    {visible && typeof document !== 'undefined' ? createPortal(
      <div ref={panel} id={id} role={open ? 'dialog' : 'tooltip'} aria-label={open ? `${skill.name} 导出记录` : undefined}
        style={position} className={`fixed z-[70] overflow-y-auto overscroll-contain rounded-lg border border-slate-200 bg-white text-slate-800 shadow-lg ${open ? '' : 'pointer-events-none'}`}>
        {open ? <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h3 className="min-w-0 break-words text-sm font-semibold">导出记录 · {entries.length}</h3>
          <button ref={closeButton} type="button" onClick={close} aria-label="关闭导出记录" className={`${actionClass} text-slate-600 hover:bg-slate-100`}>关闭</button>
        </div> : null}
        <ul className="divide-y divide-slate-100 px-4">
          {entries.map(([target, item]) => {
            const config = targets.find(t => t.id === target);
            const name = exportTargetLabel(targets, target);
            const status = sourceStatus(skill, item);
            return <li key={target} className="py-3">
              <p className="break-words text-xs font-medium">{name}{!config?.enabled ? '（已停用）' : ''}</p>
              <p className={`mt-1 text-xs ${item.stale || sourceBlocked || !item.content_hash ? 'text-amber-800' : 'text-slate-600'}`}>{status}</p>
              {open ? <>
                <p className="mt-2 break-words text-xs text-slate-500">导出时间：{item.published_at ? item.published_at.replace('T', ' ').slice(0, 16) : '未知'}</p>
                <p className="mt-1 text-xs text-slate-500">版本：<span className="font-mono" title={item.revision || item.content_hash}>{(item.revision || item.content_hash)?.slice(0, 7) || '未知版本'}</span></p>
                <div className="mt-2 flex flex-wrap items-center gap-1">
                  <button type="button" disabled={sourceBlocked || !config?.enabled} aria-label={`重新导出到 ${name}`}
                    onClick={() => {setOpen(false); setPreview(false); onExport(skill, target);}}
                    className={`${actionClass} text-sky-700 hover:bg-sky-50`}>重新导出</button>
                  <button type="button" aria-label={`清除 ${name} 导出记录`}
                    onClick={() => {setOpen(false); setPreview(false); onDeleteExport(skill, target);}}
                    className={`${actionClass} text-rose-700 hover:bg-rose-50`}>清除记录</button>
                </div>
              </> : null}
            </li>;
          })}
        </ul>
        {open ? <p className="border-t border-slate-100 px-4 py-3 text-xs leading-5 text-slate-500">仅对比当前源内容，不代表目标电脑上的实际安装状态。</p> : null}
      </div>, document.body) : null}
  </>;
}
