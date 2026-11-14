/**
 * 基金代码快速搜索（筛选 chip 行右侧，与经理页搜索框同位置）
 *
 * - 输入 6 位代码回车 → 查后端 /lookup/{code} → 跳到对应 tab，**列表里出结果**
 *   （URL 带 ?search_code=xxx，主表只显示这一只并高亮；点行才开抽屉）
 * - 只做跳转，不参与筛选状态（不写 ?qs，避免污染可分享的筛选链接）
 * - 查不到 / 接口失败 → **弹框提示**（曾经只显示一行小字，用户根本看不到）
 * - 样式对齐经理页的「搜索姓名 / 公司」框：w-36、py-0.5、text-xs、ml-auto
 *
 * 11-16 变更：命中后不再追加 `focus=1`（那会触发目标页清空筛选 + 自动弹抽屉）。
 * `path` 由后端给成 `<page>?search_code=<code>`，这里原样 push。
 */
'use client';

import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  classifyLookup, fetchFundLookup, normalizeCode, type FundLookup,
} from '@/lib/lookup';
import { buildSearchHref } from '@/lib/search-code';

interface FundCodeSearchProps {
  /** 布局类（chip 行传 ml-auto 靠右） */
  className?: string;
  /** 紧凑尺寸，用于筛选 chip 行 */
  compact?: boolean;
}

/** 查不到 / 出错时的弹框（原生 <dialog>，与 SchedulerDialog 同模式） */
function LookupAlert({
  title, message, onClose,
}: { title: string; message: string; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!el.open) el.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby="lookup-alert-title"
      onCancel={e => { e.preventDefault(); onClose(); }}
      onClick={e => { if (e.target === ref.current) onClose(); }}
      className="rounded-lg border border-rule bg-paper-card p-0 text-ink-strong backdrop:bg-black/40 max-w-[22rem]"
    >
      <div className="p-4">
        <h2 id="lookup-alert-title" className="text-sm font-semibold text-ink-strong">
          {title}
        </h2>
        <p className="mt-1.5 text-xs leading-5 text-ink-muted whitespace-pre-line">
          {message}
        </p>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            autoFocus
            className="inline-flex min-h-9 items-center justify-center rounded-md border border-rule-strong px-3 text-sm text-ink hover:bg-paper-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-info"
          >
            知道了
          </button>
        </div>
      </div>
    </dialog>
  );
}

export function FundCodeSearch({ className = '', compact = false }: FundCodeSearchProps) {
  const router = useRouter();
  const [input, setInput] = useState('');
  const [result, setResult] = useState<FundLookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  /** 弹框内容；null = 不显示 */
  const [alert, setAlert] = useState<{ title: string; message: string } | null>(null);

  const code = normalizeCode(input);
  const canSubmit = code !== null && !loading;
  const phase = classifyLookup(result, error);

  const submit = useCallback(async () => {
    if (loading) return;
    if (code === null) {
      // 输入不足/非法也给出明确反馈（按了没反应会被当成卡死）
      const raw = input.trim();
      setAlert({
        title: '请输入完整的基金代码',
        message: raw
          ? `「${raw}」不是有效的 6 位基金代码。`
          : '请输入 6 位数字的基金代码，例如 002910。',
      });
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    setAlert(null);
    try {
      const res = await fetchFundLookup(code);
      setResult(res);
      if (res.found && res.path) {
        // path 由后端给好，是相对路径（basePath 自动补前缀，不能再加 /funds）。
        // 形如 /stock?search_code=002910 —— 目标页据此把主表锁成这一只，
        // 不再清筛选、不自动弹抽屉（11-16）。点行才由用户主动打开详情。
        //
        // ⚠ 不能直接 router.push(res.path)：那会把当前筛选参数整串丢掉
        // （实测：筛着规模 ≥ 5 亿，搜完回来筛选没了）。
        // buildSearchHref 负责「同页保留筛选 / 跨页只带 search_code」。
        setInput('');
        setResult(null);
        router.push(buildSearchHref(res.path, window.location.search, window.location.pathname));
        return;
      }
      // found=false：明确弹框，而不是一行容易被忽略的小字
      setAlert({
        title: '未找到该基金',
        message:
          `代码 ${res.code} 不在基金库里。\n\n` +
          '请确认代码是否正确（6 位数字）；' +
          '如果是新基金，可能还没被采集过。',
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setAlert({
        title: '查询失败',
        message: `暂时无法查询该代码，请稍后重试。\n\n${msg.slice(0, 120)}`,
      });
    } finally {
      setLoading(false);
    }
  }, [code, input, loading, router]);

  const size = compact ? 'px-2 py-0.5 text-xs' : 'px-2 py-1 text-sm';

  return (
    <div className={`relative ${className}`}>
      <div className="relative flex items-center">
        <MagnifyingGlassIcon
          aria-hidden="true"
          className="pointer-events-none absolute left-1.5 h-3.5 w-3.5 text-ink-soft"
        />
        <input
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

      {/* 错误时保留一行轻提示作为兜底（弹框可能被浏览器拦截） */}
      {phase === 'error' && error && alert === null && (
        <span role="status" className="absolute right-0 top-full mt-1 whitespace-nowrap text-xs text-down">
          {error.slice(0, 40)}
        </span>
      )}

      {alert !== null && (
        <LookupAlert
          title={alert.title}
          message={alert.message}
          onClose={() => setAlert(null)}
        />
      )}
    </div>
  );
}
