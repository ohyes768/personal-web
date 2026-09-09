/**
 * 同类排名文字色 + 组件（fund-select 复用）
 *
 * 数据源约定：见 FundListItem.rank_ytd/_1y/_3y/_5y 字段（后端 _parse_peer_rank 解析）
 * 配色规则：3 段渐变（≤25 优秀 / 25-75 中性 / >75 落后），只保文字色，无背景
 */
import type { RankPercentile } from './types';

export function rankColor(pct: number): string {
  if (pct <= 25) return 'text-emerald-700';
  if (pct <= 75) return 'text-ink-muted';
  return 'text-orange-700';
}

/**
 * 排名文字：{pct}% + 同色温
 * 不再带背景 chip；色码直接落在百分位数字本身上（列表更克制，详情表也能复用）
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