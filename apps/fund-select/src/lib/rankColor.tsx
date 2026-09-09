/**
 * 同类排名文字色 + 组件（fund-select 复用）
 *
 * 数据源约定：见 FundListItem.rank_ytd/_1y/_3y/_5y 字段（后端 _parse_peer_rank 解析）
 * 配色规则：3 段渐变（≤25 优秀 / 25-75 中性 / >75 落后）
 */
import type { RankPercentile } from './types';

/** 文字色（详情 chip 用） */
export function rankColor(pct: number): string {
  if (pct <= 25) return 'text-emerald-700';
  if (pct <= 75) return 'text-ink-muted';
  return 'text-orange-700';
}

/** 小色点 bg 色（列表子行用，跟上行涨跌色彻底分离） */
export function rankDotColor(pct: number): string {
  if (pct <= 25) return 'bg-emerald-700';
  if (pct <= 75) return 'bg-ink-muted';
  return 'bg-orange-700';
}

/**
 * 详情页彩色 chip：{pct}% + 同色温
 * 详情 4 周期表视觉权重高，配色保留
 */
export function RankChip({ rank }: { rank: RankPercentile | null }) {
  if (!rank || rank.pct === null || rank.total === null) {
    return <span className="text-ink-soft">-</span>;
  }
  return (
    <span className={`tnum text-[10px] font-medium whitespace-nowrap ${rankColor(rank.pct)}`}>
      {rank.pct.toFixed(1)}%
    </span>
  );
}

/**
 * 列表子行：色点 + 灰文字（数字本身无涨跌色，跟上行收益绿/红彻底分离）
 * - 段位色只落在 4×4 圆点上
 * - 数字 `1.0%` 始终 ink-soft，跟上行收益色不撞
 */
export function RankInline({ rank }: { rank: RankPercentile | null }) {
  if (!rank || rank.pct === null) {
    return <span className="text-ink-soft">-</span>;
  }
  return (
    <>
      <span
        aria-hidden="true"
        className={`inline-block w-1.5 h-1.5 rounded-full ${rankDotColor(rank.pct)}`}
      />
      <span>{rank.pct.toFixed(1)}%</span>
    </>
  );
}