/**
 * 基本面评级详情弹层：五维得分 + 星级 + 完整 markdown 报告
 */
'use client';

import { Modal } from './shared-ui/Modal';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import {
  QUALITY_DIMENSION_LABELS,
  QUALITY_DIMENSION_ORDER,
  starBadgeClass,
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

export interface QualityReportModalProps {
  score: QualityScore | null;
  onClose: () => void;
}

export function QualityReportModal({ score, onClose }: QualityReportModalProps) {
  if (!score) return null;
  return (
    <Modal isOpen={!!score} onClose={onClose} title={`基本面评级 · ${score.name}（${score.code}）`} size="lg">
      <div className="space-y-4">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className={`text-2xl ${starBadgeClass(score.stars)}`}>
            {'⭐'.repeat(score.stars)}<span className="ml-1 text-sm text-ink-muted">({score.stars}/5)</span>
          </span>
          {score.boundary && <span className="text-sm text-amber-700" title="距档位边界不足 0.25 分">⚠️ {score.boundary}</span>}
          <span className="text-xs text-ink-muted">数据日期 {score.data_date} · 评分时间 {score.scored_at}</span>
        </div>

        <p className="text-sm text-ink">{score.summary}</p>

        <div className="overflow-x-auto rounded-lg border border-rule">
          <table className="w-full text-sm text-ink">
            <thead className="bg-paper-deep text-left"><tr>
              <th className="p-2 font-medium">维度</th>
              <th className="p-2 font-medium">得分</th>
            </tr></thead>
            <tbody>
              {QUALITY_DIMENSION_ORDER.map(key => (
                <tr key={key} className="border-t border-rule">
                  <td className="p-2">{QUALITY_DIMENSION_LABELS[key]}<span className="ml-1 text-xs text-ink-muted">{WEIGHT_LABEL[key]}</span></td>
                  <td className="p-2">{score.dimensions[key]} / 5</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {score.risks.length > 0 && (
          <div>
            <h3 className="mb-1 text-sm font-semibold text-ink">主要风险</h3>
            <ul className="list-disc pl-5 text-sm text-ink">
              {score.risks.map((risk, index) => <li key={index}>{risk}</li>)}
            </ul>
          </div>
        )}

        {score.watch_points.length > 0 && (
          <div>
            <h3 className="mb-1 text-sm font-semibold text-ink">关注点</h3>
            <ul className="list-disc pl-5 text-sm text-ink">
              {score.watch_points.map((point, index) => <li key={index}>{point}</li>)}
            </ul>
          </div>
        )}

        <div className="md-body max-w-none text-sm text-ink">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{score.report_md}</ReactMarkdown>
        </div>
      </div>
    </Modal>
  );
}
