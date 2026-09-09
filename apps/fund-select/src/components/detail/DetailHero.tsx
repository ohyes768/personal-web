/**
 * 详情页头部：综合评级 chip + 4 个 KPI + 基础信息行
 *
 * 设计目标：让用户在前两屏内拿到「这只基金值不值得看」的结论，
 * 4 张明细表作为补充。
 */
import type { FundDetail } from '@/lib/types';
import { Signal } from './Signal';
import { RiskMetricsGrid } from './RiskMetricsGrid';
import {
  compositeScore, gradeLabel, gradeLabelEn,
} from './score';

interface DetailHeroProps {
  fund: FundDetail;
}

/** 一句话总评：基于最强维度生成短句 */
function buildHeadline(fund: FundDetail, score: number): string {
  const r3 = fund.rank_3y;
  const pct = r3?.pct;
  const pctTxt = pct !== null && pct !== undefined && pct <= 25
    ? `近 3 年同类前 ${pct.toFixed(1)}%`
    : pct !== null && pct !== undefined && pct <= 50
      ? `近 3 年跑赢过半同行（前 ${pct.toFixed(1)}%）`
      : null;

  const alphaTxt = fund.alpha !== null && fund.alpha !== undefined && fund.alpha >= 0.05
    ? '选股贡献突出'
    : null;

  const ddTxt = fund.dd_3y !== null && fund.dd_3y !== undefined && fund.dd_3y <= 0.2
    ? '回撤控制良好'
    : fund.dd_3y !== null && fund.dd_3y !== undefined && fund.dd_3y >= 0.35
      ? '回撤较大'
      : null;

  const parts = [pctTxt, alphaTxt, ddTxt].filter((x): x is string => !!x);
  if (parts.length === 0) return score >= 75 ? '整体表现稳健' : '需结合明细进一步评估';
  return parts.join(' · ');
}

const retFmt = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;
};

const numFmt = (v: number | null | undefined, suffix = ''): string => {
  if (v === null || v === undefined) return '-';
  return `${v.toFixed(2)}${suffix}`;
};

export function DetailHero({ fund }: DetailHeroProps) {
  const { score, segment } = compositeScore(fund);
  const headline = buildHeadline(fund, score);

  // 规模：>10000 万 → 转亿；否则显示万
  const sizeText = fund.size_yi === null || fund.size_yi === undefined
    ? '-'
    : fund.size_yi >= 1
      ? `${fund.size_yi.toFixed(1)} 亿`
      : `${(fund.size_yi * 10).toFixed(1)} 千万`;

  const ret3Rank = fund.rank_3y;
  const ret3RankLabel = ret3Rank?.pct !== null && ret3Rank?.pct !== undefined
    ? `前 ${ret3Rank.pct.toFixed(1)}%`
    : '-';

  return (
    <section className="border-b border-rule-strong/40 pb-6 mb-6">
      {/* 顶部：综合评级 chip + 一句话总评 */}
      <div className="flex items-start gap-4 flex-wrap">
        <div className="flex items-baseline gap-3">
          <span className="text-[10px] uppercase tracking-[0.18em] text-ink-soft font-medium">
            综合评级 · Composite
          </span>
          <span className="text-[10px] text-ink-soft italic" style={{ fontFamily: 'var(--font-serif)' }}>
            {gradeLabelEn(segment)}
          </span>
        </div>
        <Signal segment={segment} size={9} label={`综合评级 ${segment} 段`} />
        <span className="text-2xl tnum text-ink-strong" style={{ fontFamily: 'var(--font-serif)' }}>
          {gradeLabel(segment)}
        </span>
        <span className="text-xs tnum text-ink-muted">
          {score} <span className="text-ink-soft">/ 100</span>
        </span>
      </div>

      {/* 一句话总评 */}
      <p
        className="mt-3 text-lg text-ink-strong leading-snug"
        style={{ fontFamily: 'var(--font-serif)' }}
      >
        {headline}
      </p>

      {/* 6 个风险指标卡片（3 列 × 2 行） */}
      <RiskMetricsGrid fund={fund} />

      {/* 4 个 KPI 大数字卡片 */}
      <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-px bg-rule">
        <KpiCell
          label="近 3 年收益"
          value={retFmt(fund.ret_3y)}
          sub={ret3RankLabel}
          accent={fund.ret_3y !== null && fund.ret_3y !== undefined && fund.ret_3y >= 0 ? 'up' : 'down'}
        />
        <KpiCell
          label="最大回撤"
          value={
            fund.dd_3y === null || fund.dd_3y === undefined
              ? '-'
              : `-${(fund.dd_3y * 100).toFixed(1)}%`
          }
          sub={
            fund.dd_3y !== null && fund.dd_3y !== undefined
              ? fund.dd_3y <= 0.15 ? '回撤可控'
                : fund.dd_3y <= 0.25 ? '回撤一般'
                  : fund.dd_3y <= 0.35 ? '回撤较大'
                    : '回撤很大'
              : '-'
          }
          accent={fund.dd_3y !== null && fund.dd_3y !== undefined && fund.dd_3y > 0.3 ? 'down' : undefined}
        />
        <KpiCell
          label="基金规模"
          value={sizeText}
          sub={fund.age_years !== null && fund.age_years !== undefined ? `${fund.age_years.toFixed(1)} 年` : '-'}
        />
        <KpiCell
          label="经理从业"
          value={
            fund.mgr_experience_years !== null && fund.mgr_experience_years !== undefined
              ? `${fund.mgr_experience_years.toFixed(1)} 年`
              : '-'
          }
          sub={fund.mgr_name ?? '-'}
        />
      </div>

      {/* 基础信息行 */}
      <div className="mt-4 flex items-center gap-3 text-[11px] text-ink-muted flex-wrap">
        <span className="font-mono text-info">{fund.code}</span>
        <Dot />
        <span>{fund.fund_type || '-'}</span>
        <Dot />
        {fund.established_date && (
          <>
            <span>成立 {fund.established_date}</span>
            <Dot />
          </>
        )}
        {fund.nav_latest !== null && fund.nav_latest !== undefined && (
          <>
            <span>
              最新净值 <span className="tnum text-ink-strong">{fund.nav_latest.toFixed(4)}</span>
              {fund.nav_date && <span className="ml-1 text-ink-soft">({fund.nav_date})</span>}
            </span>
            <Dot />
          </>
        )}
        {fund.is_active ? (
          <span className="text-up">· 运行中</span>
        ) : (
          <span className="text-ink-soft">· 已终止</span>
        )}
      </div>
    </section>
  );
}

/** KPI 单格：左大数字 + 底部标签 + 右侧副标 */
function KpiCell({
  label, value, sub, accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: 'up' | 'down';
}) {
  const valueClass = accent === 'up'
    ? 'text-up'
    : accent === 'down'
      ? 'text-down'
      : 'text-ink-strong';
  return (
    <div className="bg-paper-card px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.12em] text-ink-soft">{label}</div>
      <div
        className={`mt-1 text-2xl tnum font-medium ${valueClass}`}
        style={{ fontFamily: 'var(--font-serif)' }}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[11px] text-ink-muted truncate">{sub}</div>
    </div>
  );
}

function Dot() {
  return <span className="text-ink-soft">·</span>;
}
