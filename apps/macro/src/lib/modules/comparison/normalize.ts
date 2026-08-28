/**
 * 对比模块归一化工具
 * 把任意量纲的曲线在所选时间范围内首值归一为 100，显示相对涨跌
 */
import type { IndicatorId } from './types';
import type { EconomicDataResponse } from '@/lib/types/economic';

/** 从 EconomicDataResponse 抽出指定指标的原始值数组 */
export function extractSeries(
  data: EconomicDataResponse,
  id: IndicatorId
): (number | null)[] {
  switch (id) {
    case 'us_3m':  return data.us_treasuries['3m'] ?? [];
    case 'us_2y':  return data.us_treasuries['2y'] ?? [];
    case 'us_10y': return data.us_treasuries['10y'] ?? [];
    case 'cn_10y': return data.china_bond?.['10y'] ?? [];
    case 'dxy':     return data.exchange_rates?.dollar_index ?? [];
    case 'usd_cny': return data.exchange_rates?.usd_cny ?? [];
    case 'usd_jpy': return data.exchange_rates?.usd_jpy ?? [];
    case 'usd_eur': return data.exchange_rates?.usd_eur ?? [];
    case 'vix':     return data.vix ?? [];
    case 'tga':     return data.tga ?? [];
    case 'hibor':   return data.hibor ?? [];
    case 'north_net': return data.fund_flow?.north_net_flow ?? [];
    case 'south_net': return data.fund_flow?.south_net_flow ?? [];
    case 'ted_spread': return data.ted_spread?.ted_spread ?? [];
    case 'sofr':       return data.ted_spread?.sofr ?? [];
    case 'cn_10y_2y':  return data.china_bond?.['spread_10y_2y'] ?? [];
    case 'gold':   return data.commodities?.gold ?? [];
    case 'silver': return data.commodities?.silver ?? [];
    case 'oil':    return data.commodities?.oil ?? [];
    case 'copper': return data.commodities?.copper ?? [];
    case 'hk_hsi':    return data.indices?.HKHSI ?? [];
    case 'sh_000001': return data.indices?.SH000001 ?? [];
    case 'spx':       return data.indices?.SPX ?? [];
    case 'ixic':      return data.indices?.IXIC ?? [];
    case 'dji':       return data.indices?.DJI ?? [];
  }
}

/**
 * 归一化：每条线独立，第一个非 null 值 = 100，其他值按比例换算
 * - 所有 null 保留为 null（Plotly 会跳过，不画虚线）
 * - 范围内无任何有效值时返回原 series（前端会显示空 trace）
 */
export function normalize(series: (number | null)[]): (number | null)[] {
  const firstValid = series.find(v => v !== null && v !== undefined);
  if (firstValid == null || firstValid === 0) {
    return series;  // 无基准值，原样返回
  }
  return series.map(v => (v == null ? null : (v / firstValid) * 100));
}

/**
 * 满幅归一化（min-max 百分位）：每条线各自的 min = 0, max = 100
 * - 跨指标对比的标准做法：把量纲不同的曲线（HIBOR 0~5%, 恒生 15000~35000）
 *   各自拉伸到同一 Y 轴 [0, 100]，能直观看到「同向/反向」关系
 * - 所有 null 保留为 null
 * - 全部值相同时（max == min）返 50（避免除 0，画一条中线）
 * - 区间内无有效值时原样返回
 */
export function minMaxNormalize(series: (number | null)[]): (number | null)[] {
  const valid = series.filter((v): v is number => v != null && !Number.isNaN(v));
  if (valid.length === 0) return series;
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  if (max === min) {
    // 区间内恒定，画一条中位线
    return series.map(() => 50);
  }
  return series.map((v) => (v == null ? null : ((v - min) / (max - min)) * 100));
}
