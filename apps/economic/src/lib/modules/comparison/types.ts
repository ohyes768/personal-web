/**
 * 对比模块类型定义
 * 20 个可选指标，按数据源分组
 */

/** 数据源分组 */
export type IndicatorGroup =
  | 'us_treasury'
  | 'eu_treasury'
  | 'jp_treasury'
  | 'cn_treasury'
  | 'exchange'
  | 'volatility'
  | 'liquidity'
  | 'fund_flow'
  | 'rates'
  | 'commodity'
  | 'stock_index';

/** 指标 ID 联合类型（覆盖所有可对比曲线） */
export type IndicatorId =
  | 'us_3m' | 'us_2y' | 'us_10y'
  | 'eu_3m' | 'eu_2y' | 'eu_10y'
  | 'jp_10y'
  | 'cn_10y'
  | 'dxy' | 'usd_cny' | 'usd_jpy' | 'usd_eur'
  | 'vix'
  | 'tga' | 'hibor'
  | 'north_net' | 'south_net'
  | 'ted_spread' | 'sofr' | 'cn_10y_2y'
  | 'gold' | 'silver' | 'oil' | 'copper'
  | 'hk_hsi' | 'sh_000001' | 'spx' | 'ixic' | 'dji';

/** 单个指标元信息（用于 IndicatorSelector 渲染 + ComparisonChart 取数据） */
export interface IndicatorMeta {
  id: IndicatorId;
  label: string;          // 中文显示名
  group: IndicatorGroup;
  color: string;          // 曲线颜色（hex）
  unit: string;           // 单位（%, $/oz, ¥/g, 亿元等）
  source: 'FRED' | 'AKShare' | 'ECB' | '阿里云' | 'HKMA';
}
