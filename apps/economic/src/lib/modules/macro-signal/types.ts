/**
 * 宏观信号模块类型定义
 *
 * 数据契约对齐 macro-fin-skill 的 6 个子 skill 输出:
 * - skill 的 `conclusion` 字段 → MacroSignalGroup.conclusion(卡头主信号)
 * - skill 的 `details` 字段 → 拆分为 MacroIndicator 数组,每个指标带各自的 updated_at
 * - skill 的 `score` 字段 → 前端不展示,类型中也不含
 */
import type { TabType } from '@/lib/types/economic';

/** 分组 key(对齐 skill 的 dimension 字段) */
export type DimensionKey =
  | 'monetary_policy'
  | 'money_supply'
  | 'entity_economy'
  | 'inflation'
  | 'exchange_rate'
  | 'risk_appetite';

/** 单个指标(每个指标自带更新时间,粒度到指标级) */
export interface MacroIndicator {
  /** 指标 key,如 'cpi_yoy' / 'dr007',前端查 INDICATOR_LABELS 翻译 */
  key: string;
  /** 指标数值,null = 本月无数据 */
  value: number | null;
  /** 该指标的更新日期 'YYYY-MM-DD',null = 本月无数据 */
  updated_at: string | null;
}

/** 一个分组(6 大主题之一)= skill 定性结论 + 该分组下指标列表 */
export interface MacroSignalGroup {
  /** skill 的定性结论,如「温和」「适度宽松」;null = 整组缺失 */
  conclusion: string | null;
  /** 该分组下所有指标,空数组 = 整组缺失 */
  indicators: MacroIndicator[];
}

/** 一个月快照 = 6 个分组 */
export interface MacroSignalSnapshot {
  /** 'YYYY-MM' */
  month: string;
  /** 6 个分组,以 DimensionKey 索引 */
  groups: Record<DimensionKey, MacroSignalGroup>;
  /** 数据生成时间,ISO timestamp */
  generated_at?: string;
}

/** 容器组件 Props —— 切换月份 = 调 loadSnapshot */
export interface MacroSignalTabProps {
  /** 月份数据加载函数。本期父级传 loadMockSnapshot;后续 agent 替换为 API fetch */
  loadSnapshot: (month: string) => Promise<MacroSignalSnapshot | null>;
  /** 可切换的月份列表(YYYY-MM) */
  availableMonths: string[];
  /** 初始选中的月份 'YYYY-MM';不传则取 availableMonths 排序后最大值 */
  initialMonth?: string;
  /** 指标跳转回调(若该指标已有对应的曲线图 Tab),父级透传 setActiveTab */
  onJumpToTab?: (tab: TabType) => void;
}
