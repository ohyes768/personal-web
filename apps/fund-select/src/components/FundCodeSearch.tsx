/**
 * 基金代码快速搜索（header 右上角）
 *
 * - 输入 6 位代码回车 → 查后端 /lookup/{code} → 跳到对应 tab 并自动开抽屉
 * - 只做跳转，不参与筛选状态（不写 ?qs，避免污染可分享的筛选链接）
 * - 桌面：行内输入框；<640px：收成图标，点击展开覆盖式输入框
 */
'use client';

import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  classifyLookup, fetchFundLookup, normalizeCode, type FundLookup,
} from '@/lib/lookup';

export function FundCodeSearch() {
  const router = useRouter();
  const [input, setInput] = useState('');
  const [result, setResult] = useState<FundLookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);   // 小屏展开态
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const code = normalizeCode(input);
  const canSubmit = code !== null && !loading;
  const phase = classifyLookup(result, error);

  const submit = useCallback(async () => {
    if (code === null || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetchFundLookup(code);
      setResult(res);
      if (res.found && res.path) {
        // path 由后端给好，是相对路径（basePath 自动补前缀，不能再加 /funds）
        router.push(res.path);
        return;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '查询失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [code, loading, router]);

  // 小屏：展开后自动聚焦；Escape 收起
  useEffect(() => {
    if (expanded) inputRef.current?.focus();
  }, [expanded]);

  // 点击外部收起（仅小屏展开态）
  useEffect(() => {
    if (!expanded) return;
    function onDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setExpanded(false);
      }
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [expanded]);

  // 提交后清空输入与结果，避免下次打开残留
  useEffect(() => {
    if (phase === 'found') {
      setInput('');
      setResult(null);
      setExpanded(false);
    }
  }, [phase]);

  const hint =
    phase === 'not-found' ? `未找到 ${result?.code ?? ''}` :
    phase === 'error' ? (error ?? '查询失败') : null;

  return (
    <div ref={wrapRef} className="relative">
      {/* 桌面：行内输入框（≥640px） */}
      <div className="hidden sm:flex items-center gap-1">
        <div className="relative">
          <MagnifyingGlassIcon
            aria-hidden="true"
            className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-soft"
          />
          <input
            type="text"
            inputMode="numeric"
            maxLength={6}
            value={input}
            onChange={e => { setInput(e.target.value); setError(null); setResult(null); }}
            onKeyDown={e => { if (e.key === 'Enter') void submit(); }}
            placeholder="基金代码"
            aria-label="按基金代码快速查询"
            className="w-[6.5rem] pl-7 pr-2 py-1 rounded-lg border border-rule bg-paper-card text-sm text-ink-strong placeholder:text-ink-soft focus-visible:outline-2 focus-visible:outline-info"
          />
        </div>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canSubmit}
          aria-label="查询基金代码"
          className="px-2 py-1 rounded-lg text-xs bg-paper-deep text-ink-muted hover:bg-info-tint hover:text-info transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? '查询中' : '查询'}
        </button>
      </div>

      {/* 小屏：图标 → 展开覆盖式输入框 */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-label="按基金代码快速查询"
        aria-expanded={expanded}
        className="sm:hidden inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-paper-deep hover:text-info"
      >
        {expanded
          ? <XMarkIcon aria-hidden="true" className="h-5 w-5" />
          : <MagnifyingGlassIcon aria-hidden="true" className="h-5 w-5" />}
      </button>
      {expanded && (
        <div className="sm:hidden absolute right-0 top-full mt-2 z-40 w-64 p-2 rounded-lg border border-rule bg-paper-card shadow-lg">
          <input
            ref={inputRef}
            type="text"
            inputMode="numeric"
            maxLength={6}
            value={input}
            onChange={e => { setInput(e.target.value); setError(null); setResult(null); }}
            onKeyDown={e => {
              if (e.key === 'Enter') void submit();
              if (e.key === 'Escape') setExpanded(false);
            }}
            placeholder="输入 6 位基金代码"
            aria-label="按基金代码快速查询"
            className="w-full px-2 py-1.5 rounded border border-rule bg-paper-card text-sm text-ink-strong"
          />
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSubmit}
            className="mt-1.5 w-full px-2 py-1.5 rounded text-xs bg-info-tint text-info disabled:opacity-40"
          >
            {loading ? '查询中…' : '查询并跳转'}
          </button>
        </div>
      )}

      {/* 结果提示（两种布局共用） */}
      {hint !== null && (
        <span
          role="status"
          className="absolute right-0 top-full mt-1 whitespace-nowrap text-xs text-down bg-paper-card px-1.5 py-0.5 rounded border border-rule"
        >
          {hint}
        </span>
      )}
    </div>
  );
}
