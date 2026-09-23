/**
 * 分析报告看板类型 — 对接 backend/macro 报告接口
 * GET /api/macro/reports          → { reports: ReportMeta[], total }
 * GET /api/macro/reports/{id}     → ReportDetail
 */

export interface ReportMeta {
  report_id: string;
  title: string;
  source: string;
  /** 分析日期 YYYY-MM-DD */
  analyzed_at: string;
  /** 推送时间 ISO 时间戳 */
  pushed_at: string;
  url: string;
}

export interface ReportDetail extends ReportMeta {
  /** markdown 正文（后端渲染端需 sanitize） */
  content: string;
}

export interface ReportListData {
  reports: ReportMeta[];
  total: number;
}

/** 报告来源 → 中文标签映射（列表筛选与条目展示用） */
export const REPORT_SOURCE_LABELS: Record<string, string> = {
  'a-share-macro-impact-skill': 'A股宏观展望',
  'bond-market-macro-impact-skill': '利率债展望',
};
