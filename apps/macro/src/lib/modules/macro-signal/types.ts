/**
 * 宏观信号模块类型定义
 *
 * 数据契约对齐 macro-fin-skill 的 6 个子 skill 输出:
 * - skill 的 `conclusion` 字段 → MacroSignalGroup.conclusion(卡头主信号)
 * - skill 的 `total_score` 字段 → MacroSignalGroup.total_score(卡头右上角评分徽章)
 * - skill 的 `details` 字段 → 拆分为 MacroIndicator 数组,每个指标带各自的三时间
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

/** 单个指标(三时间都是指标级) */
export interface MacroIndicator {
  /** 指标 key,如 'cpi_yoy' / 'dr007',前端查 INDICATOR_LABELS 翻译 */
  key: string;
  /** 指标数值,null = 本月无数据 */
  value: number | null;
  /** 数据时间 'YYYY-MM-DD'(指标数值所属/发布日期),null = 本月无数据 */
  data_date?: string | null;
  /** 分析时间(skill 生成该值的时间,ISO timestamp,如 '2026-05-22T07:59:22Z') */
  analyzed_at?: string | null;
  /** 下个周期预期发布日期 'YYYY-MM-DD'(skill 自报优先,后端规则兜底;仅月频指标展示) */
  next_release_at?: string | null;
  /** 预期口径说明,如「CPI/PPI 约每月9日发布上月数据」(悬浮展示) */
  next_release_note?: string | null;
  /** 发布频率 'daily'(日频,不渲染「下次」段) | 'monthly'(月频);null = 未知按月频处理 */
  frequency?: 'daily' | 'monthly' | null;
  /** 兼容别名 = data_date,后端双写过渡,前端迁移完成后删除 */
  updated_at: string | null;
}

/** 一个分组(6 大主题之一)= skill 定性结论 + 综合评分 + 该分组下指标列表 */
export interface MacroSignalGroup {
  /** skill 的定性结论,如「温和」「适度宽松」;null = 整组缺失 */
  conclusion: string | null;
  /** 维度总分(0-100,skill 评分框架输出);null/缺省 = 未提供,不显示徽章 */
  total_score?: number | null;
  /** 该分组下所有指标,空数组 = 整组缺失 */
  indicators: MacroIndicator[];
}

/** 一个月快照 = 6 个分组 */
export interface MacroSignalSnapshot {
  /** 'YYYY-MM' */
  month: string;
  /** 6 个分组,以 DimensionKey 索引 */
  groups: Record<DimensionKey, MacroSignalGroup>;
  /** 全页最新分析时间 = 所有指标 analyzed_at 的最大值,ISO timestamp */
  generated_at?: string;
}

/** 容器组件 Props —— 切换月份 = 调 loadSnapshot */
export interface MacroSignalTabProps {
  /** 月份数据加载函数:fetch /api/macro/signal,返回 null=该月无数据 */
  loadSnapshot: (month: string) => Promise<MacroSignalSnapshot | null>;
  /** 可切换的月份列表(YYYY-MM) */
  availableMonths: string[];
  /** 初始选中的月份 'YYYY-MM';不传则取 availableMonths 排序后最大值 */
  initialMonth?: string;
  /** 指标跳转回调(若该指标已有对应的曲线图 Tab),父级透传 setActiveTab */
  onJumpToTab?: (tab: TabType) => void;
}
