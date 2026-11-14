/**
 * 共享顶部 header：左侧「← 返回首页 + 标题」+ 中部 tab 导航
 * （债基·雪球三分法 | 股基·雪球三分法 | 债基·市场 | 股基·市场）
 * 右侧 slot 由调用方传入（导出 / 刷新 / 总数 / 筛选按钮）
 *
 * 各 tab 通过 `<FundsHeader active="bond" right={...}>` 等传入。
 *
 * 注意：discovery-* tab 只有一个「全量刷新」按钮（5 阶段流水线已内置 fund_name_em 拉名单）；
 * 老 tab 的「刷新」按钮保留（刷新 yaml 名单 60 只的业绩）。
 */
'use client';

import { useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { Cog6ToothIcon, FunnelIcon } from '@heroicons/react/24/outline';

import { discoveryBondApi, discoveryStockApi } from '@/lib/api';
import { FundCodeSearch } from './FundCodeSearch';
import { FundsNavigation } from './FundsNavigation';
import { FullRefreshDialog } from './FullRefreshDialog';
import { RefreshStatusPopover } from './RefreshStatusPopover';
import { SchedulerDialog } from './SchedulerDialog';
import type { FullRefreshFilters, RefreshStatus } from '@/lib/types';

export type FundsTab = 'bond' | 'stock' | 'discovery-bond' | 'discovery-stock' | 'managers';

interface FundsHeaderProps {
  active: FundsTab;
  total: number;
  /** 总数单位：基金 tab 是「只」，经理 tab 是「人」 */
  totalUnit?: string;
  activeFilterCount: number;
  onOpenMobileFilter: () => void;
  /** 「债基」时由父级调 reset 回调；「股票」也同 */
  onRefreshed: () => void;
  /** 刷新接口选择：'stock' → /funds/api/funds/stock/*，
   *  'discovery-bond'/'discovery-stock' → /funds/api/funds/discovery-*，
   *  'managers' → /funds/api/funds/managers/refresh */
  exportKind: FundsTab;
  /** 全量 refresh 完成回调（仅 discovery-* tab 传）：同步预筛选值到左侧 */
  onFullRefreshComplete?: (preFilters: FullRefreshFilters) => void;
  /** 当前生效的预筛选值（用于初始化弹窗 default） */
  preFilters?: FullRefreshFilters;
  /** 是否显示「基金代码快速搜索」框（仅四个基金 tab 传 true；
   *  经理/榜单/走势页复用同一 header 但不需要，默认 false） */
  showCodeSearch?: boolean;
}

const TITLE: Record<FundsTab, string> = {
  'bond': '债基·雪球三分法',
  'stock': '股基·雪球三分法',
  'discovery-bond': '债基·市场',
  'discovery-stock': '股基·市场',
  'managers': '经理·股票基金',
};

/** tab 的 refresh 端点（bond / stock 刷 yaml 名单业绩；managers 刷经理档案）。
 *  discovery-* tab 已合并到「全量刷新」按钮（pipeline L0 自动跑 fund_name_em）。 */
const REFRESH_URL: Partial<Record<FundsTab, string>> = {
  'bond': '/funds/api/funds/refresh',
  'stock': '/funds/api/funds/stock/refresh',
  'managers': '/funds/api/funds/managers/refresh',
};

/** discovery-* tab 的全量 refresh：start 闭包 + poll 闭包（避免组件持有 URL 字符串） */
const FULL_REFRESH_API: Partial<Record<FundsTab, {
  startFullRefresh: (filters: FullRefreshFilters) => Promise<{ task_id: string; status: string }>;
  pollFullRefreshStatus: (taskId: string) => Promise<RefreshStatus>;
}>> = {
  'discovery-bond': {
    startFullRefresh: (filters: FullRefreshFilters) => discoveryBondApi.fullRefresh(filters),
    pollFullRefreshStatus: (taskId: string) => discoveryBondApi.getFullRefreshStatus(taskId),
  },
  'discovery-stock': {
    startFullRefresh: (filters: FullRefreshFilters) => discoveryStockApi.fullRefresh(filters),
    pollFullRefreshStatus: (taskId: string) => discoveryStockApi.getFullRefreshStatus(taskId),
  },
};

export function FundsHeader({
  active,
  total,
  totalUnit = '只',
  activeFilterCount,
  onOpenMobileFilter,
  onRefreshed,
  exportKind,
  onFullRefreshComplete,
  preFilters,
  showCodeSearch = false,
}: FundsHeaderProps) {
  const title = TITLE[active];
  const refreshUrl = REFRESH_URL[exportKind];
  const statusUrl = refreshUrl ? `${refreshUrl}/status` : undefined;
  const fullRefreshApi = FULL_REFRESH_API[exportKind];

  const [fullOpen, setFullOpen] = useState(false);
  const searchParams = useSearchParams();
  const [schedulerOpen, setSchedulerOpen] = useState(searchParams.get('scheduler') === '1');

  return (
    <header className="border-b border-rule bg-paper-card sticky top-0 z-30">
      <div className="max-w-[1400px] mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <a
            href="/"
            className="text-xs text-ink-muted hover:text-ink-strong transition-colors"
          >
            ← 返回首页
          </a>
          <div className="flex items-baseline gap-3 mt-0.5 flex-wrap">
            <h1 className="text-lg font-semibold text-ink-strong">{title}</h1>
            <FundsNavigation active={active} />
          </div>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          {refreshUrl && (
            <RefreshStatusPopover
              refreshUrl={refreshUrl}
              statusUrl={statusUrl}
              onRefreshed={onRefreshed}
            />
          )}
          {fullRefreshApi && onFullRefreshComplete && (
            <>
              <button
                onClick={() => setFullOpen(true)}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-paper-deep text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
                aria-label="全量刷新"
              >
                全量刷新
              </button>
              <FullRefreshDialog
                open={fullOpen}
                onClose={() => setFullOpen(false)}
                startFullRefresh={fullRefreshApi.startFullRefresh}
                pollFullRefreshStatus={fullRefreshApi.pollFullRefreshStatus}
                onComplete={(pf) => {
                  setFullOpen(false);
                  onFullRefreshComplete(pf);
                  onRefreshed();
                }}
                initial={preFilters}
              />
            </>
          )}
          {showCodeSearch && <FundCodeSearch />}
          <span className="hidden sm:inline text-sm text-ink-muted">
            共 <span className="tnum font-semibold text-ink-strong">{total}</span> {totalUnit}
          </span>
          <button
            onClick={onOpenMobileFilter}
            className="lg:hidden inline-flex items-center gap-1 px-2.5 py-1.5 text-sm rounded-lg bg-paper-deep text-ink-muted"
            aria-label="打开筛选"
          >
            <FunnelIcon className="w-4 h-4" />
            筛选{activeFilterCount > 0 && <span className="text-info">({activeFilterCount})</span>}
          </button>
          <button type="button" onClick={() => setSchedulerOpen(true)} aria-label="定时任务" title="定时任务" aria-haspopup="dialog" className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-paper-deep hover:text-info focus-visible:outline-2 focus-visible:outline-info">
            <Cog6ToothIcon aria-hidden="true" className="h-5 w-5" />
          </button>
        </div>
      </div>
      {schedulerOpen && <SchedulerDialog onClose={() => setSchedulerOpen(false)} />}
    </header>
  );
}
