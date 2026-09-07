/**
 * 债基 tab 行点击详情抽屉
 *
 * 沿用 RowDetailDrawer 风格：mask + 右侧 fixed + Escape + body overflow 锁定 + 响应式宽度。
 * 内容：基础信息（代码/名称/类型） + 持仓分析（券种饼图 + 集中度 + 前五大） + 费率明细。
 * 加载：useEffect 监听 fund.code → fundApi.getDetail；骨架屏渲染。
 */
'use client';

import { useEffect, useState } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';

import type { FundDetail, FundListItem } from '@/lib/types';
import { fundApi } from '@/lib/api';
import { FEE_ROWS } from '@/lib/feeRows';

/** 券种配置：手写 SVG 圆环 4 段拼接 */
const HOLDING_COLORS = {
  rate:        'var(--color-info)',          // 深蓝灰 - 低风险
  credit:      'var(--color-accent)',        // 暖橘红 - 中风险
  convertible: 'var(--color-up)',            // 绿色   - 权益属性
  other:       'var(--color-rule-strong)',   // 灰色   - 中性
} as const;

interface DonutSegment {
  label: string;
  pct: number;
  color: string;
}

/** DonutChart：4 段手写 SVG 圆环；missing 段按 0；其他 = 100 - 已知之和 */
function DonutChart({ rate, credit, convertible }: {
  rate: number | null;
  credit: number | null;
  convertible: number | null;
}) {
  const segments: DonutSegment[] = [
    { label: '利率债', pct: rate ?? 0,        color: HOLDING_COLORS.rate },
    { label: '信用债', pct: credit ?? 0,      color: HOLDING_COLORS.credit },
    { label: '可转债', pct: convertible ?? 0, color: HOLDING_COLORS.convertible },
  ];
  const sumKnown = segments.reduce((s, x) => s + x.pct, 0);
  const other = Math.max(0, 100 - sumKnown);
  // 仅在 > 0.5% 时添加"其他"段，避免噪声
  if (other > 0.5) {
    segments.push({ label: '其他', pct: other, color: HOLDING_COLORS.other });
  }

  // 圆环中线半径 = 50，viewBox 120×120，留 10px padding
  const C = 2 * Math.PI * 50;

  let offset = 0;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 120 120" className="w-32 h-32 shrink-0" role="img" aria-label="券种配置">
        {segments.map((s, i) => {
          const len = (s.pct / 100) * C;
          // 段长 0 时不渲染 circle，避免 strokeDasharray="0 314" 视觉异常
          if (len <= 0) return null;
          const dasharray = `${len} ${C - len}`;
          const dashoffset = -offset;
          offset += len;
          return (
            <circle
              key={i}
              cx="60" cy="60" r="50"
              fill="none"
              stroke={s.color}
              strokeWidth="20"
              strokeDasharray={dasharray}
              strokeDashoffset={dashoffset}
              transform="rotate(-90 60 60)"
            />
          );
        })}
        <text x="60" y="60" textAnchor="middle" dy="0.35em" className="text-[10px] fill-ink-muted">
          券种
        </text>
      </svg>
      <ul className="text-xs space-y-1.5">
        {segments.map(s => (
          <li key={s.label} className="flex items-center gap-2">
            <span
              className="inline-block w-3 h-3 rounded-sm shrink-0"
              style={{ background: s.color }}
              aria-hidden="true"
            />
            <span className="text-ink-strong">{s.label}</span>
            <span className="text-ink-muted tnum ml-auto">{s.pct.toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 持仓集中度进度条：0-50% 量程；≤30 绿 / 30-50 黄 / >50 红 */
function ConcentrationBar({ pct }: { pct: number | null }) {
  const max = 50;
  const displayPct = pct === null ? 0 : Math.min(pct, max);
  const ratio = max > 0 ? (displayPct / max) * 100 : 0;
  let color = 'bg-paper-deep';
  if (pct !== null) {
    if (pct <= 30) color = 'bg-up';
    else if (pct <= 50) color = 'bg-star';
    else color = 'bg-down';
  }
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-ink-strong">前 5 大债券占比</span>
        <span className="text-sm tnum text-ink-strong font-medium">
          {pct === null ? '-' : `${pct.toFixed(1)}%`}
        </span>
      </div>
      <div className="h-2 bg-paper-deep rounded-full overflow-hidden" aria-hidden="true">
        <div
          className={`h-full ${color} transition-all`}
          style={{ width: `${ratio}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-ink-soft">
        <span>0%</span>
        <span>30%（分散）</span>
        <span>50%（集中）</span>
      </div>
    </div>
  );
}

/** top5_bonds 字符串解析：`21民生银行永续债01(6.8%); 25进出01(2.6%); ...` → 数组 */
function parseTop5Bonds(s: string | null | undefined): Array<{ name: string; pct: number }> {
  if (!s) return [];
  return s.split('; ')
    .map(line => {
      const m = line.match(/^(.+?)\(([\d.]+)%\)$/);
      if (!m) return null;
      return { name: m[1], pct: Number(m[2]) };
    })
    .filter((x): x is { name: string; pct: number } => x !== null);
}

interface RowDetailDrawerBondProps {
  fund: FundListItem | null;
  onClose: () => void;
}

export function RowDetailDrawerBond({ fund, onClose }: RowDetailDrawerBondProps) {
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

  // 监听 fund.code 拉详情（债基路由）
  useEffect(() => {
    if (!fund) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setDetail(null);
    let cancelled = false;
    fundApi.getDetail(fund.code)
      .then(d => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setDetail(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fund?.code]);

  if (!fund) return null;

  // 响应式宽度（沿用 RowDetailDrawer）
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
        aria-labelledby="row-detail-drawer-bond-title"
        tabIndex={-1}
      >
        {/* 头部 */}
        <div className="sticky top-0 z-10 bg-gray-900 border-b border-gray-700">
          <div className="flex items-center justify-between px-6 py-4">
            <div className="min-w-0 flex-1">
              <h2 id="row-detail-drawer-bond-title" className="text-base font-semibold text-ink-strong truncate">
                <span className="font-mono text-info mr-2">{fund.code}</span>
                {fund.name}
              </h2>
              <p className="text-xs text-ink-muted mt-0.5 truncate">{fund.fund_type || '-'}</p>
            </div>
            <button
              onClick={onClose}
              className="min-h-10 min-w-10 flex items-center justify-center text-gray-400 hover:text-ink-strong hover:bg-gray-700 rounded transition-colors"
              aria-label="关闭详情"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* 内容 */}
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-6">
          {loading && !detail && <SkeletonSection />}

          {detail && (
            <>
              {/* 表 1：持仓分析 */}
              <RankTable
                title={detail.holdings?.report_date
                  ? `持仓分析（${detail.holdings.report_date} 报告期）`
                  : '持仓分析'}
              >
                {!detail.holdings ? (
                  <p className="text-xs text-ink-soft text-center py-4">暂无持仓数据</p>
                ) : (
                  <div className="space-y-5">
                    {/* 1-A 券种配置饼图 */}
                    <div>
                      <h4 className="text-xs font-medium text-ink-muted mb-2">券种配置</h4>
                      <DonutChart
                        rate={detail.holdings.rate_bond_pct}
                        credit={detail.holdings.credit_bond_pct}
                        convertible={detail.holdings.convertible_pct}
                      />
                    </div>

                    {/* 1-B 持仓集中度 */}
                    <div>
                      <h4 className="text-xs font-medium text-ink-muted mb-2">持仓集中度</h4>
                      <ConcentrationBar pct={detail.holdings.top5_concentration} />
                    </div>

                    {/* 1-C 前五大债券明细 */}
                    <div>
                      <h4 className="text-xs font-medium text-ink-muted mb-2">前五大债券明细</h4>
                      <Top5Table top5Bonds={detail.holdings.top5_bonds} />
                    </div>
                  </div>
                )}
              </RankTable>

              {/* 表 2：费率明细 */}
              <RankTable title="费率明细">
                <table className="w-full text-xs">
                  <tbody>
                    {FEE_ROWS.map(row => {
                      const v = detail.fees?.[row.key];
                      return (
                        <tr key={row.key} className="border-b border-rule">
                          <td className="py-1.5 text-ink-strong">{row.label}</td>
                          <td className="py-1.5 text-right tnum text-ink-muted">
                            {v === null || v === undefined
                              ? '-'
                              : `${v.toFixed(2)}%${row.suffix ?? ''}`}
                          </td>
                        </tr>
                      );
                    })}
                    <tr className="border-b border-rule bg-paper-tint">
                      <td className="py-1.5 text-ink-strong font-medium">年费合计</td>
                      <td className="py-1.5 text-right tnum text-ink-strong font-medium">
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
              </RankTable>

              {/* 口径脚注 */}
              <p className="text-[10px] leading-relaxed text-ink-soft">
                数据口径：持仓来自最近一期基金季报（占净值比例）；利率债 / 信用债 / 可转债按债券名称分类（参见 bond_classifier）。
                "其他" = 100% − 已知三档之和（现金 / 同业存单 / ABS 等）。费率为基金销售 / 管理费率（不含业绩报酬 / 申购费优惠）。
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}

/** Top5 债券明细子组件 */
function Top5Table({ top5Bonds }: { top5Bonds: string | null }) {
  const items = parseTop5Bonds(top5Bonds);
  if (items.length === 0) {
    return <p className="text-xs text-ink-soft text-center py-3">暂无明细</p>;
  }
  // 已按 desc 排序（prepend 后再展示）；若需要可再排
  return (
    <table className="w-full text-xs">
      <thead className="text-ink-muted border-b border-rule">
        <tr>
          <th className="text-left py-1 font-medium">债券名称</th>
          <th className="text-right py-1 font-medium w-[5rem]">占比</th>
        </tr>
      </thead>
      <tbody>
        {items.map((it, i) => (
          <tr key={`${i}-${it.name}`} className="border-b border-rule last:border-b-0">
            <td className="py-1.5 text-ink-strong truncate" title={it.name}>{it.name}</td>
            <td className="py-1.5 text-right tnum text-ink-muted">{it.pct.toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** 子组件：带标题的表卡片（与 RowDetailDrawer 同款） */
function RankTable({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-sm font-medium text-ink-strong mb-2">{title}</h3>
      <div className="rounded border border-rule bg-gray-900 p-3">{children}</div>
    </section>
  );
}

/** 骨架屏：2 张表占位 */
function SkeletonSection() {
  return (
    <div className="space-y-6">
      {[0, 1].map(i => (
        <section key={i}>
          <div className="h-4 w-24 bg-paper-deep rounded mb-2 animate-pulse" />
          <div className="rounded border border-rule bg-gray-900 p-3 space-y-2">
            {Array.from({ length: 4 }).map((_, j) => (
              <div
                key={j}
                className="h-3 bg-paper-deep rounded animate-pulse"
                style={{ width: `${60 + j * 8}%` }}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
