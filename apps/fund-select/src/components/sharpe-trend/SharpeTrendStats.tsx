/**
 * 夏普走势稳定性 KPI 卡片行
 *
 * 六格主 KPI（当前 / 区间最高 / 最低 / 均值 / 达标率 / 最近连续达标）
 * + 一行次级信息（最长连续低于阈值 / 近 12 周趋势斜率 / 数据口径说明）。
 *
 * 语义：达标 = 周点夏普 ≥ threshold（默认 0.8，与夏普榜单入选线一致）；
 * None 值显示 '—'，不冒充 0。配色沿用 app 的 ink/down/up 语义。
 */
'use client';

import {
  formatRatio,
  formatSharpe,
  formatSlope,
  sharpeLevel,
  type SharpeTrendStats,
} from '@/lib/sharpe-trend';

interface KpiCellProps {
  label: string;
  value: string;
  sub?: string;
  level?: 'good' | 'bad' | 'na' | 'neutral';
  emphasis?: boolean;
}

function KpiCell({ label, value, sub, level = 'neutral', emphasis = false }: KpiCellProps) {
  const valueColor =
    level === 'good' ? 'text-up' : level === 'bad' || level === 'na' ? 'text-down' : 'text-ink-strong';
  return (
    <div className={`rounded-lg border border-rule bg-paper-card px-3 py-2.5 min-w-0 ${emphasis ? 'ring-1 ring-info/30' : ''}`}>
      <div className="text-[11px] text-ink-muted truncate" title={label}>{label}</div>
      <div className={`mt-1 text-lg font-semibold tnum truncate ${valueColor}`} title={value}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-ink-soft truncate" title={sub}>{sub}</div>}
    </div>
  );
}

interface SharpeTrendStatsProps {
  stats: SharpeTrendStats;
  rfBasis: string;
  algorithmVersion: string;
  pointCount: number;
}

export function SharpeTrendStatsPanel({
  stats, rfBasis, algorithmVersion, pointCount,
}: SharpeTrendStatsProps) {
  const th = stats.threshold;
  const currentLevel = sharpeLevel(stats.current, th);

  return (
    <section aria-label="稳定性指标" className="bg-paper-card rounded-lg border border-rule p-3">
      <div className="flex items-baseline justify-between gap-2 flex-wrap mb-2.5">
        <h2 className="text-sm font-medium text-ink-strong">稳定性指标</h2>
        <span className="text-[11px] text-ink-soft">
          达标线 {th.toFixed(2)} · 展示区间 {pointCount} 个周点 · 有效 {stats.valid_count} 点
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <KpiCell
          label="当前夏普"
          value={formatSharpe(stats.current)}
          sub="最新周点"
          level={currentLevel}
          emphasis
        />
        <KpiCell label="区间最高" value={formatSharpe(stats.max)} sub="最好水平" level="good" />
        <KpiCell label="区间最低" value={formatSharpe(stats.min)} sub="最差水平" level="bad" />
        <KpiCell label="区间均值" value={formatSharpe(stats.mean)} sub="整体水平" />
        <KpiCell
          label="达标率"
          value={formatRatio(stats.above_ratio)}
          sub={`${stats.above_count} / ${stats.valid_count} 周`}
        />
        <KpiCell
          label="最近连续达标"
          value={`${stats.consecutive_above} 周`}
          sub="从最新点往回"
          level={stats.consecutive_above > 0 ? 'good' : 'bad'}
        />
      </div>

      <div className="mt-2.5 pt-2.5 border-t border-rule/60 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-ink-muted">
        <span>
          最长连续低于 {th.toFixed(2)}：
          <b className={stats.longest_below > 0 ? 'text-down' : 'text-up'}>{stats.longest_below} 周</b>
        </span>
        <span>
          近 12 周趋势：<b className="text-ink-strong">{formatSlope(stats.trend_12w)}</b>
        </span>
        <span className="text-ink-soft" title="夏普 = 近 3 年滚动 mean/标准差 × √252；不 join 基准">
          口径 {algorithmVersion} · 无风险利率：{rfBasis === 'zero' ? '按 0（利率表为空）' : '库内利率'}
        </span>
      </div>
    </section>
  );
}
