'use client';

import { useEffect, useRef, useState } from 'react';
import type { InstallTarget } from '@/lib/installTargets';

interface ProfileScopePickerProps {
  current: string;
  /**
   * 全部 installTargets（含 removed），picker 内部对 popover 列表做 !removed 过滤。
   * 传完整列表是为了让 button 仍能显示已移除的当前 target（design §6 「已移除态」）。
   */
  allTargets: InstallTarget[];
  loading: boolean;
  error: string;
  onSelect: (id: string) => void;
  onManage: () => void;
  onRefresh: () => void;
}

type Status = 'available' | 'unavailable' | 'removed' | 'loading' | 'error' | 'invalid';

/** provider 字段在数据里固定小写，渲染时按 label 映射大写显示（design §3 mockup）。 */
const PROVIDER_LABEL: Record<InstallTarget['provider'], string> = {
  hermes: 'Hermes',
};

const DOT_CLASS: Record<Status, string> = {
  available: 'bg-emerald-500',
  unavailable: 'bg-amber-500',
  removed: 'bg-slate-300',
  loading: 'bg-slate-300 animate-pulse',
  error: 'bg-rose-500',
  invalid: 'bg-amber-500',
};

const TRIGGER_CLASS: Record<Status, string> = {
  available: 'border-slate-300 hover:bg-slate-50',
  unavailable: 'border-amber-400 hover:bg-amber-50',
  removed: 'border-slate-200 hover:bg-slate-50',
  loading: 'border-slate-200 hover:bg-slate-50',
  error: 'border-rose-400 hover:bg-rose-50',
  invalid: 'border-amber-400 hover:bg-amber-50',
};

function classify(
  allTargets: InstallTarget[],
  current: string,
  loading: boolean,
  error: string,
): { status: Status; target: InstallTarget | undefined } {
  if (loading) return { status: 'loading', target: undefined };
  if (error) return { status: 'error', target: undefined };
  const found = allTargets.find((t) => t.id === current);
  if (!found) return { status: 'invalid', target: undefined };
  if (found.removed) return { status: 'removed', target: found };
  if (!found.available) return { status: 'unavailable', target: found };
  return { status: 'available', target: found };
}

function triggerText(target: InstallTarget | undefined, status: Status, currentId: string): string {
  if (status === 'loading') return '加载中…';
  if (status === 'error') return '加载失败，点击重试';
  if (status === 'invalid') return `${currentId}（不可用）`;
  const identity = `${PROVIDER_LABEL[target!.provider]} · ${target!.profile_name}`;
  if (status === 'removed') return `${identity}（已移除）`;
  if (status === 'unavailable') {
    const reason = target!.unavailable_reason?.split('\n')[0] ?? '目标不可用';
    return `目标不可用：${reason}`;
  }
  return identity;
}

export default function ProfileScopePicker({
  current,
  allTargets,
  loading,
  error,
  onSelect,
  onManage,
  onRefresh,
}: ProfileScopePickerProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  const { status, target } = classify(allTargets, current, loading, error);
  const labelText = triggerText(target, status, current);

  useEffect(() => {
    if (!open || typeof document === 'undefined') return;
    function onDoc(e: MouseEvent) {
      if (popRef.current?.contains(e.target as Node)) return;
      if (triggerRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const handleTriggerClick = () => {
    // 错误态点击 = 触发刷新（design §6），其它态 = 切换 popover。
    if (status === 'error') {
      onRefresh();
      return;
    }
    setOpen((o) => !o);
  };

  const visibleTargets = allTargets.filter((t) => !t.removed);

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={handleTriggerClick}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`当前发布目标：${labelText}`}
        className={`flex items-center rounded-md border bg-white px-3 py-1.5 text-sm text-slate-700 transition-colors ${TRIGGER_CLASS[status]}`}
      >
        <span
          className={`mr-2 inline-block h-2 w-2 rounded-full ${DOT_CLASS[status]}`}
          aria-hidden="true"
        />
        <span className="max-w-[200px] truncate">{labelText}</span>
        <span className="ml-1 text-slate-400" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div
          ref={popRef}
          role="dialog"
          aria-label="切换发布目标"
          className="absolute right-0 top-full z-30 mt-1 w-[360px] rounded-md border border-slate-200 bg-white shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <h3 className="text-sm font-medium text-slate-700">切换发布目标</h3>
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="text-xs text-sky-700 underline disabled:opacity-50"
            >
              {loading ? '刷新中…' : '刷新'}
            </button>
          </div>
          <ul className="max-h-72 overflow-y-auto py-1">
            {visibleTargets.length === 0 && (
              <li className="px-3 py-4 text-center text-sm text-slate-400">暂无 profile</li>
            )}
            {visibleTargets.map((t) => {
              const isActive = t.id === current;
              const itemDot = t.available ? 'bg-emerald-500' : 'bg-amber-500';
              const reasonLine = !t.available && t.unavailable_reason
                ? t.unavailable_reason.split('\n')[0]
                : '';
              return (
                <li key={t.id}>
                  <button
                    type="button"
                    onClick={() => {
                      if (loading) return;
                      onSelect(t.id);
                      setOpen(false);
                    }}
                    data-active={isActive}
                    disabled={loading}
                    className="flex w-full items-start gap-2 border-l-2 border-transparent px-3 py-2 text-left text-sm hover:bg-slate-50 disabled:opacity-50 data-[active=true]:border-sky-500 data-[active=true]:bg-sky-50"
                  >
                    <span
                      className={`mt-1 h-2 w-2 shrink-0 rounded-full ${itemDot}`}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-slate-800">
                          {PROVIDER_LABEL[t.provider]} · {t.profile_name}
                        </span>
                        <span
                          aria-hidden="true"
                          className={t.available ? 'text-xs text-slate-400' : 'text-xs text-amber-600'}
                        >
                          {t.available ? '✓' : '⚠'}
                        </span>
                      </span>
                      <code
                        className="mt-0.5 block truncate rounded bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-500"
                        title={t.install_path}
                      >
                        {t.install_path}
                      </code>
                      {reasonLine && (
                        <p className="mt-0.5 text-[11px] text-amber-700">{reasonLine}</p>
                      )}
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        已安装 {t.active_installation_count ?? 0} 个 Skill
                      </p>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="border-t border-slate-100 px-3 py-2">
            <button
              type="button"
              onClick={() => {
                onManage();
                setOpen(false);
              }}
              className="text-xs text-sky-700 underline"
            >
              管理安装目标 →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
