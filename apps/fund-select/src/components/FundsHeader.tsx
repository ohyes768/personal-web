/**
 * 共享顶部 header：左侧「← 返回首页 + 标题」+ 中部 tab 导航（债基 | 股票）
 * 右侧 slot 由调用方传入（导出 / 刷新 / 总数 / 筛选按钮）
 *
 * 债基页 <FundsHeader active="bond" right={...}>，
 * 股票页 <FundsHeader active="stock" right={...}>。
 */
'use client';

import Link from 'next/link';

import { FunnelIcon } from '@heroicons/react/24/outline';

import { RefreshStatusPopover } from './RefreshStatusPopover';
import type { FundFilters } from '@/lib/types';

interface FundsHeaderProps {
  active: 'bond' | 'stock';
  total: number;
  activeFilterCount: number;
  onOpenMobileFilter: () => void;
  /** 「债基」时由父级调 reset 回调；「股票」也同 */
  onRefreshed: () => void;
  filters: FundFilters;
  /** 刷新接口选择：'stock' → /funds/stock/*，'bond' → /funds/* */
  exportKind: 'bond' | 'stock';
}

export function FundsHeader({
  active,
  total,
  activeFilterCount,
  onOpenMobileFilter,
  onRefreshed,
  filters,
  exportKind,
}: FundsHeaderProps) {
  const title = active === 'bond' ? '债券基金筛选' : '股票基金筛选';
  return (
    <header className="border-b border-rule bg-paper-card sticky top-0 z-30">
      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* 原生 <a> 而非 Link：basePath=/funds 会把 Link 的 href="/" 拼成 /funds */}
          <a
            href="/"
            className="text-xs text-ink-muted hover:text-ink-strong transition-colors"
          >
            ← 返回首页
          </a>
          <div className="flex items-baseline gap-3 mt-0.5">
            <h1 className="text-lg font-semibold text-ink-strong">{title}</h1>
            <nav className="flex items-center gap-0.5 text-sm">
              {/* Link 的 href 相对 basePath：/bond → /funds/bond */}
              <TabLink href="/bond" active={active === 'bond'}>债基</TabLink>
              <TabLink href="/stock" active={active === 'stock'}>股票</TabLink>
            </nav>
          </div>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <RefreshStatusPopover
            refreshUrl={exportKind === 'stock' ? '/funds/api/funds/stock/refresh' : undefined}
            statusUrl={exportKind === 'stock' ? '/funds/api/funds/stock/refresh/status' : undefined}
            onRefreshed={onRefreshed}
          />
          <span className="hidden sm:inline text-sm text-ink-muted">
            共 <span className="tnum font-semibold text-ink-strong">{total}</span> 只
          </span>
          <button
            onClick={onOpenMobileFilter}
            className="lg:hidden inline-flex items-center gap-1 px-2.5 py-1.5 text-sm rounded-lg bg-paper-deep text-ink-muted"
            aria-label="打开筛选"
          >
            <FunnelIcon className="w-4 h-4" />
            筛选{activeFilterCount > 0 && <span className="text-info">({activeFilterCount})</span>}
          </button>
        </div>
      </div>
    </header>
  );
}

function TabLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className={`px-2 py-0.5 rounded transition-colors ${
        active
          ? 'bg-accent text-white'
          : 'text-ink-muted hover:text-ink-strong'
      }`}
    >
      {children}
    </Link>
  );
}
