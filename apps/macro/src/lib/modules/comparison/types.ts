/**
 * 对比模块类型定义
 * 可选指标按数据源分组
 */

/** 数据源分组 */
export type IndicatorGroup =
  | 'us_treasury'
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
  | 'cn_10y'
  | 'dxy' | 'usd_cny' | 'usd_jpy' | 'usd_eur'
  | 'vix'
  | 'tga' | 'hibor'
  | 'north_deal' | 'south_net'
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
  source: 'FRED' | 'AKShare' | '阿里云' | 'HKMA' | '东财';
}

/**
 * 对比图表的渲染模式（用户手动切换，不做自动判定）
 * - minMax:                  满幅百分位（每条线 min=0, max=100，跨指标对比的标准做法）
 * - normalize:               起点归一 100，单 Y 轴（适合同质指标看相对涨跌，如美债 2y + 10y）
 * - dualAxis:                真实值，按 unit 种类分左右轴（看绝对水平）
 * - dualAxisWithCorrelation: 双轴 + 下方 30 日滚动 Pearson 相关性子图（仅 2 个指标时可用）
 */
export type ViewMode = 'minMax' | 'normalize' | 'dualAxis' | 'dualAxisWithCorrelation';
