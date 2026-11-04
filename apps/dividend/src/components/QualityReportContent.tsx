/**
 * 基本面评级报告正文（弹窗与阅读页共享）
 *
 * 只渲染五维得分、分析元数据与 Markdown 正文；
 * 不渲染 weighted_score / stars / boundary（契约：未评级不合成总分与星级）。
 * variant='modal' 保持原弹窗观感；variant='reader' 用于手机长文阅读。
 */
'use client';

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { QualitySkillVersion } from './QualitySkillVersion';
import {
  QUALITY_DIMENSION_LABELS,
  QUALITY_DIMENSION_ORDER,
  formatAnalysisDuration,
  type QualityDimensionKey,
  type QualityScore,
} from '@/lib/quality';

const WEIGHT_LABEL: Record<QualityDimensionKey, string> = {
  business: '25%',
  moat: '25%',
  industry: '20%',
  management: '15%',
  financial: '15%',
};

export interface QualityReportContentProps {
  score: QualityScore;
  /** 当前已部署的 skill 版本；用于提示「需重评」 */
  currentSkillVersion?: string | null;
  /** 展示形态：弹窗（紧凑）或阅读页（长文） */
  variant?: 'modal' | 'reader';
}

/** 阅读页变体：表格局部横滑，不撑破整页 */
const readerMarkdownComponents: Components = {
  table: ({ node: _node, ...props }) => (
    <div className="quality-reader-table-wrap">
      <table {...props} />
    </div>
  ),
};

export function QualityReportContent({ score, currentSkillVersion, variant = 'modal' }: QualityReportContentProps) {
  const isReader = variant === 'reader';

  return (
    <div className={isReader ? 'quality-reader-content space-y-5' : 'space-y-4'}>
      {isReader ? (
        // 阅读页：三项各自成行，避免长文本在手机上从中间断开
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-ink-muted">
          <span>数据日期 {score.data_date}</span>
          <span>评分时间 {score.scored_at}</span>
          <span>分析耗时 {formatAnalysisDuration(score.analysis_duration_seconds)}</span>
        </div>
      ) : (
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="text-xs text-ink-muted">
            数据日期 {score.data_date} · 评分时间 {score.scored_at} · 分析耗时 {formatAnalysisDuration(score.analysis_duration_seconds)}
          </span>
        </div>
      )}

      <QualitySkillVersion version={score.skill_version} currentVersion={currentSkillVersion} />

      {isReader && <h2 className="quality-reader-section">摘要</h2>}
      <p className={isReader ? 'quality-reader-text' : 'text-sm text-ink'}>{score.summary}</p>

      {isReader && <h2 className="quality-reader-section">五维评分</h2>}
      <div className={isReader ? 'quality-reader-table-wrap rounded-lg border border-rule' : 'overflow-x-auto rounded-lg border border-rule'}>
        <table className={isReader ? 'quality-reader-text w-full' : 'w-full text-sm text-ink'}>
          <thead className="bg-paper-deep text-left"><tr>
            <th className="p-2 font-medium">维度</th>
            <th className="p-2 font-medium">得分</th>
          </tr></thead>
          <tbody>
            {QUALITY_DIMENSION_ORDER.map(key => (
              <tr key={key} className="border-t border-rule">
                <td className="p-2">{QUALITY_DIMENSION_LABELS[key]}<span className="ml-1 text-xs text-ink-muted">{WEIGHT_LABEL[key]}</span></td>
                <td className="p-2">{score.dimensions[key] == null ? <span className="text-ink-muted">未评分</span> : `${score.dimensions[key]} / 5`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {score.risks.length > 0 && (
        <div>
          <h3 className={isReader ? 'quality-reader-section' : 'mb-1 text-sm font-semibold text-ink'}>主要风险</h3>
          <ul className={isReader ? 'quality-reader-list' : 'list-disc pl-5 text-sm text-ink'}>
            {score.risks.map((risk, index) => <li key={index}>{risk}</li>)}
          </ul>
        </div>
      )}

      {score.watch_points.length > 0 && (
        <div>
          <h3 className={isReader ? 'quality-reader-section' : 'mb-1 text-sm font-semibold text-ink'}>关注点</h3>
          <ul className={isReader ? 'quality-reader-list' : 'list-disc pl-5 text-sm text-ink'}>
            {score.watch_points.map((point, index) => <li key={index}>{point}</li>)}
          </ul>
        </div>
      )}

      {isReader && <h2 className="quality-reader-section">完整报告</h2>}
      {score.report_md?.trim() ? (
        <div className={isReader ? 'md-body quality-reader-md' : 'md-body max-w-none text-sm text-ink'}>
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={isReader ? readerMarkdownComponents : undefined}>
            {score.report_md}
          </ReactMarkdown>
        </div>
      ) : (
        <p className={isReader ? 'quality-reader-text text-ink-muted' : 'text-sm text-ink-muted'}>暂无完整报告正文</p>
      )}
    </div>
  );
}
