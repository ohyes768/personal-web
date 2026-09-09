/**
 * 同类排名 chip 颜色 + 组件（fund-select 复用）
 *
 * 数据源约定：见 FundListItem.rank_ytd/_1y/_3y/_5y 字段（后端 _parse_peer_rank 解析）
 * 颜色规则：5 段渐变（≤10 优秀 / ≤25 良好 / ≤50 中性 / ≤75 偏弱 / 落后）
 */
import type { RankPercentile } from './types';

export function rankColor(pct: number): string {
  if (pct <= 10)  return 'bg-rank-top text-white';
  if (pct <= 25)  return 'bg-rank-top-soft text-rank-top-strong';
  if (pct <= 50)  return 'bg-rank-mid text-ink-muted';
  if (pct <= 75)  return 'bg-rank-bottom-soft text-rank-bottom-strong';
  return 'bg-rank-bottom text-white';
}

/**
 * 排名 chip：前 {pct}% + tooltip 显示原始排名/总数
 * 从 pct/total 反推整数排名（与雪球原始字符串四舍五入近似）
 */
export function RankChip({ rank }: { rank: RankPercentile | null }) {
  if (!rank || rank.pct === null || rank.total === null) {
    return <span className="text-ink-soft">-</span>;
  }
  const originalRank = Math.round(rank.pct * rank.total / 100);
  const tooltip = `${originalRank}/${rank.total}`;
  return (
    <span
      className={`tnum text-[10px] px-1 py-0.5 rounded font-medium whitespace-nowrap hover-tip ${rankColor(rank.pct)}`}
      data-tip={tooltip}
      aria-label={`同类排名 ${tooltip}`}
    >
      前 {rank.pct.toFixed(1)}%
    </span>
  );
}
