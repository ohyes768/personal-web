/**
 * 基本面评级详情弹层：重评工具条 + 共享报告正文
 * 正文内容与手机阅读页共用 QualityReportContent，行为与样式保持不变。
 */
'use client';

import { Modal } from './shared-ui/Modal';
import { QualityReportContent } from './QualityReportContent';
import type { QualityScore } from '@/lib/quality';

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
        <QualityReportContent score={score} currentSkillVersion={currentSkillVersion} />
      </div>
    </Modal>
  );
}
