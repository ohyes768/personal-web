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
    case 'eu_3m':  return data.eu_treasuries['3m'] ?? [];
    case 'eu_2y':  return data.eu_treasuries['2y'] ?? [];
    case 'eu_10y': return data.eu_treasuries['10y'] ?? [];
    case 'jp_10y': return data.jp_treasuries['10y'] ?? [];
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
