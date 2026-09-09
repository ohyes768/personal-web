/**
 * 行点击详情抽屉（股票 tab）
 *
 * 结构：
 *   1. 头部（代码 + 名称 + 类型 + 关闭按钮）
 *   2. DetailHero（综合评级 + 6 指标卡片 + 4 个 KPI + 基础信息行）
 *   3. 3 张明细表（同类排名 / 历年年度业绩 / 费率明细）
 *
 * 沿用 CompareDrawer 风格：mask + 右侧 fixed drawer + Escape 关闭 + body overflow 锁定。
 */
'use client';

import { useEffect, useState } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';

import type { FundDetail, FundListItem } from '@/lib/types';
import { stockApi } from '@/lib/api';
import { RankChip } from '@/lib/rankColor';
import { FEE_ROWS } from '@/lib/feeRows';

import { DetailHero } from './detail/DetailHero';

/** 与后端 RANK_PERIODS 对齐：4 周期主表顺序 */
const PERIODS: Array<{ kind: string; period: string; label: string }> = [
  { kind: '年度业绩', period: '今年以来', label: '今年以来' },
  { kind: '阶段业绩', period: '近1年',    label: '近 1 年' },
  { kind: '阶段业绩', period: '近3年',    label: '近 3 年' },
  { kind: '阶段业绩', period: '近5年',    label: '近 5 年' },
];

/** 排序历年年度业绩：数字年份 desc；"今年以来"置顶；"成立以来"末位 */
function sortAnnualRanks(ranks: FundDetail['achievement_ranks']) {
  return [...ranks]
    .filter(r => r.period_kind === '年度业绩')
    .sort((a, b) => {
      if (a.period === '成立以来') return 1;
      if (b.period === '成立以来') return -1;
      if (a.period === '今年以来') return -1;
      if (b.period === '今年以来') return 1;
      return Number(b.period) - Number(a.period);
    });
}

/** 风险拆解块字段定义已迁移至 detail/RiskMetricsGrid.tsx（Hero 区第 3 块） */

interface RowDetailDrawerProps {
  fund: FundListItem | null;
  onClose: () => void;
}

export function RowDetailDrawer({ fund, onClose }: RowDetailDrawerProps) {
  const [detail, setDetail] = useState<FundDetail | null>(null);
  const [loading, setLoading] = useState(false);

  // Escape 关闭 + body overflow 锁定
  useEffect(() => {
    if (!fund) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [fund, onClose]);

  // 监听 fund.code 拉详情
  useEffect(() => {
    if (!fund) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setDetail(null);
    let cancelled = false;
    stockApi.getDetail(fund.code)
      .then(d => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setDetail(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fund?.code]);

  if (!fund) return null;

  // 响应式宽度（沿用 CompareDrawer）
  const width = typeof window === 'undefined'
    ? 'w-[60vw]'
    : window.innerWidth >= 1280 ? 'w-[900px]'
      : window.innerWidth >= 1024 ? 'w-[60vw]'
        : window.innerWidth >= 768 ? 'w-[70vw]'
          : window.innerWidth >= 640 ? 'w-[90vw]'
            : 'w-[95vw]';

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity duration-300"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`fixed top-0 right-0 bottom-0 z-50 bg-gray-900 shadow-xl transform transition-transform duration-300 flex flex-col ${width}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="row-detail-drawer-title"
        tabIndex={-1}
      >
        {/* 头部：标题行 + 关闭按钮 */}
        <div className="sticky top-0 z-10 bg-gray-900 border-b border-rule">
          <div className="flex items-start justify-between px-6 pt-5 pb-4 gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-3">
                <span
                  className="font-mono text-info text-xs tracking-wide"
                >
                  {fund.code}
                </span>
                {fund.fund_type && (
                  <span className="text-[10px] uppercase tracking-[0.12em] text-ink-soft">
                    {fund.fund_type}
                  </span>
                )}
              </div>
              <h2
                id="row-detail-drawer-title"
                className="mt-1 text-xl text-ink-strong leading-tight"
                style={{ fontFamily: 'var(--font-serif)', fontWeight: 600 }}
              >
                {fund.name}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="min-h-10 min-w-10 flex items-center justify-center text-gray-400 hover:text-ink-strong hover:bg-gray-700 rounded transition-colors shrink-0"
              aria-label="关闭详情"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* 内容 */}
        <div className="overflow-y-auto flex-1 px-6 py-6 space-y-7">
          {loading && !detail && <SkeletonSection />}

          {detail && (
            <>
              {/* Hero：综合评级 + 4 个 KPI + 基础信息行 */}
              <DetailHero fund={detail} />

              {/* 表 1：4 周期排名 */}
              <DetailSection
                eyebrow="业绩排名"
                title="同类排名 · 4 周期"
                caption="雪球蛋卷基金同类区间排序（分母随时间变化）"
              >
                <table className="w-full text-xs">
                  <thead className="text-ink-muted border-b border-rule">
                    <tr>
                      <th className="text-left py-1.5 font-medium">周期</th>
                      <th className="text-right py-1.5 font-medium">收益</th>
                      <th className="text-right py-1.5 font-medium">百分位</th>
                      <th className="text-right py-1.5 font-medium">同类排名</th>
                    </tr>
                  </thead>
                  <tbody>
                    {PERIODS.map(p => {
                      const row = detail.achievement_ranks.find(
                        r => r.period_kind === p.kind && r.period === p.period
                      );
                      const ret = row?.ret ?? null;
                      const retClass = ret === null
                        ? 'text-ink-soft'
                        : ret >= 0 ? 'text-up' : 'text-down';
                      const retText = ret === null ? '-' : `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`;
                      const rankPct = (() => {
                        if (!row?.peer_rank) return null;
                        const parts = row.peer_rank.split('/');
                        if (parts.length !== 2) return null;
                        const r = Number(parts[0]);
                        const t = Number(parts[1]);
                        if (!r || !t || r > t) return null;
                        return { pct: Math.round(r / t * 1000) / 10, total: t, rank: r };
                      })();
                      return (
                        <tr key={p.label} className="border-b border-rule last:border-b-0">
                          <td className="py-2 text-ink-strong">{p.label}</td>
                          <td className={`py-2 text-right tnum ${retClass}`}>{retText}</td>
                          <td className="py-2 text-right"><RankChip rank={rankPct} /></td>
                          <td className="py-2 text-right tnum text-ink-muted">{row?.peer_rank || '-'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </DetailSection>

              {/* 表 2：历年年度业绩 */}
              <DetailSection
                eyebrow="历史业绩"
                title="历年年度业绩"
                caption="每自然年完整年度收益（成立不足一年按实际交易日折算）"
              >
                <table className="w-full text-xs">
                  <thead className="text-ink-muted border-b border-rule">
                    <tr>
                      <th className="text-left py-1.5 font-medium">年份</th>
                      <th className="text-right py-1.5 font-medium">收益</th>
                      <th className="text-right py-1.5 font-medium">百分位</th>
                      <th className="text-right py-1.5 font-medium">同类排名</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const annuals = sortAnnualRanks(detail.achievement_ranks);
                      if (annuals.length === 0) {
                        return (
                          <tr><td colSpan={4} className="py-3 text-center text-ink-soft">暂无年度业绩数据</td></tr>
                        );
                      }
                      return annuals.map(r => {
                        const ret = r.ret;
                        const retClass = ret === null
                          ? 'text-ink-soft'
                          : ret >= 0 ? 'text-up' : 'text-down';
                        const retText = ret === null ? '-' : `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`;
                        const rankPct = (() => {
                          if (!r.peer_rank) return null;
                          const parts = r.peer_rank.split('/');
                          if (parts.length !== 2) return null;
                          const rr = Number(parts[0]);
                          const tt = Number(parts[1]);
                          if (!rr || !tt || rr > tt) return null;
                          return { pct: Math.round(rr / tt * 1000) / 10, total: tt, rank: rr };
                        })();
                        return (
                          <tr key={r.period_kind + r.period} className="border-b border-rule last:border-b-0">
                            <td className="py-2 text-ink-strong">{r.period}</td>
                            <td className={`py-2 text-right tnum ${retClass}`}>{retText}</td>
                            <td className="py-2 text-right"><RankChip rank={rankPct} /></td>
                            <td className="py-2 text-right tnum text-ink-muted">{r.peer_rank || '-'}</td>
                          </tr>
                        );
                      });
                    })()}
                  </tbody>
                </table>
              </DetailSection>

              {/* 表 4：费率明细 */}
              <DetailSection
                eyebrow="持有成本"
                title="费率明细"
                caption="申购费 / 赎回费 / 管理费 / 托管费 / 服务费合计"
              >
                <table className="w-full text-xs">
                  <tbody>
                    {FEE_ROWS.map(row => {
                      const v = detail.fees?.[row.key];
                      return (
                        <tr key={row.key} className="border-b border-rule">
                          <td className="py-2 text-ink-strong">{row.label}</td>
                          <td className="py-2 text-right tnum text-ink-muted">
                            {v === null || v === undefined
                              ? '-'
                              : `${v.toFixed(2)}%${row.suffix ?? ''}`}
                          </td>
                        </tr>
                      );
                    })}
                    <tr className="border-b border-rule bg-paper-tint">
                      <td className="py-2 text-ink-strong font-medium">年费合计</td>
                      <td className="py-2 text-right tnum text-ink-strong font-medium">
                        {(() => {
                          const m = detail.fees?.fee_mgmt;
                          const c = detail.fees?.fee_custody;
                          const s = detail.fees?.fee_service ?? 0;
                          if (m === null || m === undefined || c === null || c === undefined) return '-';
                          return `${(m + c + (s ?? 0)).toFixed(2)}%/年`;
                        })()}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </DetailSection>

              {/* 口径脚注 */}
              <p className="text-[10px] leading-relaxed text-ink-soft pt-2 border-t border-rule">
                数据口径：排名来自雪球蛋卷基金（同类基金区间收益排序，分母随时间变化）；
                费率为基金销售/管理费率（不含业绩报酬/申购费优惠）。点击列头或悬停可看更多解释。
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}

/** 子组件：分节卡片（左 eyebrow + 主标题 + caption + 内容） */
function DetailSection({
  eyebrow, title, caption, children,
}: {
  eyebrow?: string;
  title: string;
  caption?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <header className="mb-2">
        {eyebrow && (
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-soft">
            {eyebrow}
          </div>
        )}
        <h3
          className="text-base text-ink-strong"
          style={{ fontFamily: 'var(--font-serif)', fontWeight: 600 }}
        >
          {title}
        </h3>
        {caption && (
          <p className="text-[11px] text-ink-muted mt-0.5">{caption}</p>
        )}
      </header>
      <div className="rounded border border-rule bg-paper-card p-3">
        {children}
      </div>
    </section>
  );
}

/** 骨架屏：Hero 占位 + 4 张表占位 */
function SkeletonSection() {
  return (
    <div className="space-y-7">
      <section>
        <div className="h-3 w-24 bg-paper-deep rounded mb-3 animate-pulse" />
        <div className="h-6 w-3/4 bg-paper-deep rounded animate-pulse" />
        <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-px bg-rule">
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="bg-paper-card px-4 py-3 space-y-2">
              <div className="h-2 w-12 bg-paper-deep rounded animate-pulse" />
              <div className="h-6 w-20 bg-paper-deep rounded animate-pulse" />
              <div className="h-2 w-16 bg-paper-deep rounded animate-pulse" />
            </div>
          ))}
        </div>
      </section>
      {[0, 1, 2, 3].map(i => (
        <section key={i}>
          <div className="h-3 w-16 bg-paper-deep rounded mb-2 animate-pulse" />
          <div className="h-5 w-32 bg-paper-deep rounded mb-1 animate-pulse" />
          <div className="rounded border border-rule bg-paper-card p-3 space-y-2">
            {Array.from({ length: 4 }).map((_, j) => (
              <div key={j} className="h-3 bg-paper-deep rounded animate-pulse" style={{ width: `${60 + j * 8}%` }} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
