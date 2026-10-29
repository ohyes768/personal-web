/**
 * 基本面评级详情弹层：五维得分、分析元数据与完整 markdown 报告
 */
'use client';

import { Modal } from './shared-ui/Modal';
import { QualitySkillVersion } from './QualitySkillVersion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
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

export interface QualityReportModalProps {
  currentSkillVersion?: string | null;
  score: QualityScore | null;
  onClose: () => void;
  /** 提供时渲染「重评」入口；不提供时行为与原先一致（按钮不渲染） */
  onReanalyze?: (code: string) => void;
  /** 全局评级任务进度（展示用；按钮状态按本股票的 reanalyzePending 决定） */
  progress?: { processed: number; total: number } | null;
  /** 这只股票的评级正在排队/运行：按钮置灰 */
  reanalyzePending?: boolean;
  /** 重评不可用（如 Hermes 未配置）；按钮置灰并给出原因 */
  reanalyzeDisabled?: boolean;
}

export function QualityReportModal({ score, onClose, onReanalyze, currentSkillVersion, progress = null, reanalyzePending = false, reanalyzeDisabled = false }: QualityReportModalProps) {
  if (!score) return null;
  const jobRunning = !!progress && progress.processed < progress.total;
  return (
    <Modal isOpen={!!score} onClose={onClose} title={`基本面评级 · ${score.name}（${score.code}）`} size="lg">
      <div className="space-y-4">
        {onReanalyze && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-rule bg-paper-card px-3 py-2">
            <span className="text-sm text-ink-muted">
              {reanalyzePending
                ? '该股票评级进行中，完成后自动刷新…'
                : jobRunning
                  ? `评级任务进行中 ${progress?.processed ?? 0}/${progress?.total ?? 1}，这只股票可同时提交排队`
                  : '用当前数据重新评级（每只约几分钟）'}
            </span>
            <button
              className="rounded border border-rule-strong px-3 py-2 text-sm text-ink hover:border-accent disabled:opacity-40"
              disabled={reanalyzePending || reanalyzeDisabled}
              title={reanalyzePending ? '评级任务进行中，完成后自动刷新' : reanalyzeDisabled ? 'Hermes 未配置（需 HERMES_BASE_URL 与 HERMES_API_KEY），无法评级' : undefined}
              onClick={() => onReanalyze(score.code)}
            >
              {reanalyzePending ? '评级中…' : '重评'}
            </button>
          </div>
        )}
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="text-xs text-ink-muted">数据日期 {score.data_date} · 评分时间 {score.scored_at} · 分析耗时 {formatAnalysisDuration(score.analysis_duration_seconds)}</span>
        </div>

        <QualitySkillVersion version={score.skill_version} currentVersion={currentSkillVersion} />
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
                  <td className="p-2">{score.dimensions[key] == null ? <span className="text-ink-muted">未评分</span> : `${score.dimensions[key]} / 5`}</td>
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
