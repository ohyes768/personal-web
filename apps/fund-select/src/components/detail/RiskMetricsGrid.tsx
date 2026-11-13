/**
 * 6 个风险指标卡片网格（Hero 区第 3 块）
 *
 * 从原 RowDetailDrawer 的"风险拆解" section 提升到 Hero 区，3 列 × 2 行。
 * 每个卡片：标签 + 信号灯 + 大数字 + 评级 + 阈值参考。
 */
'use client';

import Link from 'next/link';

import type { FundDetail } from '@/lib/types';

import {
  scoreAlpha, scoreAlphaIR, scoreExcess3y, scoreGamma, scoreIR, scoreSharpe,
  type Segment,
} from './score';
import { Signal } from './Signal';

type RiskScoreFn = (v: number | null | undefined) => Segment;

const RISK_VERDICT: Record<Segment, string> = {
  0: '无数据',
  1: '偏弱',
  2: '一般',
  3: '良好',
  4: '卓越',
};

interface RiskField {
  key: 'sharpe' | 'ir' | 'alpha' | 'gamma' | 'alpha_ir' | 'excess_3y';
  label: string;
  tip: string;
  score: RiskScoreFn;
  fmt: (v: number | null | undefined) => string;
  threshold: string;
  /** true = 按数值正负染色（α / 超额）；false = 仅负数染色（夏普 / IR / γ / α-IR） */
  signed: boolean;
}

const RISK_FIELDS: RiskField[] = [
  {
    key: 'sharpe', label: '夏普比率',
    tip: '夏普比率：每承担 1 份波动，换来的超额收益（相对无风险利率）。>1 优秀；<0 意味着近 3 年还没跑赢无风险收益',
    score: scoreSharpe,
    fmt: v => v === null || v === undefined ? '-' : v.toFixed(2),
    threshold: '阈值 ≥1.5 卓越 · ≥1 良好 · <0 偏弱',
    signed: false,
  },
  {
    key: 'ir', label: 'IR 信息比率',
    tip: '信息比率：每 1 份偏离基准的波动，换来的稳定超额，衡量跑赢基准的性价比。>0.5 良好，>1 优秀',
    score: scoreIR,
    fmt: v => v === null || v === undefined ? '-' : v.toFixed(2),
    threshold: '阈值 ≥1 卓越 · ≥0.6 良好 · <0 偏弱',
    signed: false,
  },
  {
    key: 'alpha', label: '选股 α',
    tip: '选股α：剔除市场涨跌与择时贡献后，经理纯靠选股获得的年化超额收益。越高选股能力越强；持续为负 = 选股在拖后腿',
    score: scoreAlpha,
    fmt: v => v === null || v === undefined ? '-' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`,
    threshold: '阈值 ≥10% 卓越 · ≥5% 良好 · <-5% 偏弱',
    signed: true,
  },
  {
    key: 'gamma', label: '择时 γ',
    tip: '择时γ：市场大涨大跌前调仓的能力。>0 涨时跟得上、跌时躲得开；≈0 基本不择时；<0 疑似追涨杀跌',
    score: scoreGamma,
    fmt: v => v === null || v === undefined ? '-' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`,
    threshold: '阈值 ≥0.10 卓越 · ≥0.05 良好 · <-0.05 偏弱',
    signed: false,
  },
  {
    key: 'alpha_ir', label: 'α-IR',
    tip: 'α-IR：选股α的稳定度（α÷其波动）。>1 选股能力稳定可信；<0.5 说明 α 忽有忽无，参考价值低',
    score: scoreAlphaIR,
    fmt: v => v === null || v === undefined ? '-' : v.toFixed(2),
    threshold: '阈值 ≥1 卓越 · ≥0.6 良好 · <0 偏弱',
    signed: false,
  },
  {
    key: 'excess_3y', label: '超额 3y',
    tip: '近 3 年累计跑赢基准的幅度（复利口径）',
    score: scoreExcess3y,
    fmt: v => v === null || v === undefined ? '-' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`,
    threshold: '阈值 ≥40% 卓越 · ≥20% 良好 · <-10% 偏弱',
    signed: true,
  },
];

interface RiskMetricsGridProps {
  fund: FundDetail;
  /** 夏普卡片可点跳「夏普走势」页（仅股基抽屉传；债基第一版不支持）。
   *  不传时组件行为与旧版一致。 */
  trendHref?: string;
}

export function RiskMetricsGrid({ fund, trendHref }: RiskMetricsGridProps) {
  return (
    <div className="mt-5 grid grid-cols-2 md:grid-cols-3 gap-2">
      {RISK_FIELDS.map(f => {
        const v = fund[f.key];
        const seg = f.score(v);
        const isMissing = v === null || v === undefined;

        const valueClass = isMissing
          ? 'text-ink-soft'
          : f.signed
            ? (v as number) >= 0 ? 'text-up' : 'text-down'
            : (v as number) >= 0 ? 'text-ink-strong' : 'text-down';

        const verdictClass = seg >= 3
          ? 'text-up'
          : seg === 2
            ? 'text-ink-muted'
            : seg === 1
              ? 'text-down'
              : 'text-ink-soft';

        const isSharpeLink = f.key === 'sharpe' && !!trendHref;
        const cardClass = `rounded-md border border-rule bg-paper-tint/40 p-3 hover:border-rule-strong transition-colors block ${isSharpeLink ? 'hover:bg-info-tint/40 cursor-pointer' : ''}`;

        // 只有夏普卡片（且传了 href）才是链接；其余保持普通 div。
        // 显式分支而非动态 Wrapper：避免 TS 把 Link 的必填 href 强加给 div 分支。
        const body = (
          <>
            <div className="flex items-baseline justify-between gap-2">
              <span
                className="text-[11px] uppercase tracking-[0.12em] text-ink-soft font-medium"
                title={f.tip}
              >
                {f.label}
              </span>
              {!isMissing && (
                <Signal
                  segment={seg}
                  size={6}
                  label={`${f.label} ${RISK_VERDICT[seg]}`}
                />
              )}
            </div>
            <div className="mt-1.5 flex items-baseline gap-2">
              <span
                className={`text-xl tnum font-medium leading-none ${valueClass}`}
                style={{ fontFamily: 'var(--font-serif)' }}
              >
                {f.fmt(v)}
              </span>
              <span className={`text-[11px] font-medium ${verdictClass}`}>
                {RISK_VERDICT[seg]}
              </span>
              {isSharpeLink && (
                <span className="ml-auto text-[10px] text-info whitespace-nowrap">看走势 →</span>
              )}
            </div>
            <div className="mt-1.5 text-[10px] text-ink-soft leading-snug">
              {f.threshold}
            </div>
          </>
        );

        return isSharpeLink ? (
          <Link
            key={f.key}
            href={trendHref as string}
            title="查看夏普走势（完整滚动曲线）"
            className={cardClass}
          >
            {body}
          </Link>
        ) : (
          <div key={f.key} className={cardClass}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
