/**
 * 基金代码快速搜索（筛选 chip 行右侧，与经理页搜索框同位置）
 *
 * - 输入 6 位代码回车 → 查后端 /lookup/{code} → 跳到对应 tab 并自动开抽屉
 * - 只做跳转，不参与筛选状态（不写 ?qs，避免污染可分享的筛选链接）
 * - 样式对齐经理页的「搜索姓名 / 公司」框：w-40、py-0.5、text-xs、ml-auto
 * - compact：由 FilterChipBar 传入，使用该行的紧凑尺寸
 */
'use client';

import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import { useRouter } from 'next/navigation';
import { useCallback, useRef, useState } from 'react';

import {
  classifyLookup, fetchFundLookup, normalizeCode, type FundLookup,
} from '@/lib/lookup';

interface FundCodeSearchProps {
  /** 布局类（chip 行传 ml-auto 靠右） */
  className?: string;
  /** 紧凑尺寸，用于筛选 chip 行 */
  compact?: boolean;
}

export function FundCodeSearch({ className = '', compact = false }: FundCodeSearchProps) {
  const router = useRouter();
  const [input, setInput] = useState('');
  const [result, setResult] = useState<FundLookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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
        // 清空放在跳转前：跳转后组件可能卸载，此处同步清理最安全
        setInput('');
        setResult(null);
        router.push(res.path);
        return;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '查询失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [code, loading, router]);

  const hint =
    phase === 'not-found' ? `未找到 ${result?.code ?? ''}` :
    phase === 'error' ? (error ?? '查询失败') : null;

  const size = compact
    ? 'px-2 py-0.5 text-xs'
    : 'px-2 py-1 text-sm';

  return (
    <div className={`relative ${className}`}>
      <div className="relative flex items-center">
        <MagnifyingGlassIcon
          aria-hidden="true"
          className="pointer-events-none absolute left-1.5 h-3.5 w-3.5 text-ink-soft"
        />
        <input
          ref={inputRef}
          type="text"
          inputMode="numeric"
          maxLength={6}
          value={input}
          onChange={e => { setInput(e.target.value); setError(null); setResult(null); }}
          onKeyDown={e => { if (e.key === 'Enter') void submit(); }}
          placeholder={compact ? '基金代码' : '输入 6 位基金代码'}
          aria-label="按基金代码快速查询"
          disabled={loading}
          className={`w-36 pl-6 pr-2 border border-rule rounded bg-paper-card text-ink-strong focus:outline-none focus:border-info disabled:opacity-50 ${size}`}
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canSubmit}
          aria-label="查询基金代码"
          className={`ml-1 rounded text-info underline-offset-2 hover:underline disabled:opacity-40 disabled:cursor-not-allowed ${compact ? 'text-xs px-1 py-0.5' : 'text-sm px-2 py-1'}`}
        >
          {loading ? '查询中' : '查询'}
        </button>
      </div>
      {/* 结果提示：贴在这一行下方，不撑高布局 */}
      {hint !== null && (
        <span
          role="status"
          className="absolute right-0 top-full mt-1 z-20 whitespace-nowrap text-xs text-down bg-paper-card px-1.5 py-0.5 rounded border border-rule shadow-sm"
        >
          {hint}
        </span>
      )}
    </div>
  );
}
