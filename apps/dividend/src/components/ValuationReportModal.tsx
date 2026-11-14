/**
 * ValuationReportModal — 四挡位估值报告阅读与应用面板
 *
 * 内容：身份/期间/版本/耗时、四份价格（重评时对比旧生效值划线）、summary、
 * risks/data_gaps/invalidation_conditions、report_md 安全 Markdown（react-markdown + remark-gfm，
 * 同 quality-reader 渲染约定）。
 * 底部：确认应用（仅 ready；写入四条价格线）与 暂不应用。
 * 非 ready（insufficient_data/blocked/not_applicable）展示原因与缺口，不渲染任何价格，不可应用。
 */
'use client';

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { Modal } from './shared-ui/Modal';
import { SessionDownloadButton } from './SessionDownloadButton';
import {
  VALUATION_LEVEL_KEYS,
  VALUATION_LEVEL_LABEL,
  VALUATION_STATUS_LABEL,
  formatValuationDuration,
  type ValuationLevelKey,
  type ValuationReportRecord,
} from '@/lib/valuation';
import { dividendApi } from '@/lib/api';
import type { AlertLevels } from '@/lib/types';

const markdownComponents: Components = {
  table: ({ node: _node, ...props }) => (
    <div className="quality-reader-table-wrap">
      <table {...props} />
    </div>
  ),
};

export interface ValuationReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  report: ValuationReportRecord | null;
  /** 当前生效挡位（重评对比时划线显示旧值） */
  effectiveLevels: AlertLevels | null;
  /** 当前部署 skill 版本，不同则提示需重评 */
  currentSkillVersion?: string | null;
  /** 确认应用（仅 ready 且后端校验通过） */
  onApply: (report: ValuationReportRecord) => Promise<void> | void;
  /** 从报告发起重新评估 */
  onReevaluate?: (code: string) => void;
  applyPending?: boolean;
  applyError?: string;
}

const LEVEL_META: Record<ValuationLevelKey, { color: string }> = {
  heavy_position: { color: '#5A9472' },
  add_position: { color: '#C9951F' },
  reduce_position: { color: '#D4893A' },
  full_exit: { color: '#9B2F2F' },
};

export function ValuationReportModal({
  isOpen, onClose, report, effectiveLevels, currentSkillVersion,
  onApply, onReevaluate, applyPending = false, applyError = '',
}: ValuationReportModalProps) {
  if (!report) return null;
  const isReady = report.status === 'ready';
  const versionMismatch = !!currentSkillVersion && report.skill_version != null
    && report.skill_version !== currentSkillVersion;
  const hasOld = isReady && !!effectiveLevels && VALUATION_LEVEL_KEYS.some(k => effectiveLevels[k]?.price);

  // 底部操作区：固定在弹框底部，正文滚动时按钮始终可见
  const footer = (
    <div>
      {applyError && <p role="alert" className="mb-2 text-sm text-red-600">{applyError}</p>}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-xs text-ink-muted">
          {isReady
            ? hasOld
              ? '确认后替换当前四条价格线，监控继续开启。'
              : '确认后保存四条价格线，并开启价格提醒。'
            : '当前报告未生成价格，仅阅读。'}
        </p>
        <div className="flex items-center gap-2">
          {onReevaluate && (
            <button
              type="button"
              className="rounded border border-rule-strong px-3 py-1.5 text-sm text-ink hover:bg-paper-tint"
              onClick={() => onReevaluate(report.code)}
            >
              重新评估
            </button>
          )}
          <button
            type="button"
            className="rounded border border-rule-strong px-3 py-1.5 text-sm text-ink hover:bg-paper-tint"
            onClick={onClose}
          >
            {isReady ? '暂不应用' : '返回列表'}
          </button>
          {isReady && (
            <button
              type="button"
              disabled={applyPending}
              className="rounded bg-accent px-3.5 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              data-testid="valuation-apply-button"
              onClick={() => void onApply(report)}
            >
              {applyPending ? '应用中…' : hasOld ? '对比并应用' : '确认并使用挡位'}
            </button>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`${report.name} · 四挡位估值报告`}
      size="lg"
      footer={footer}
    >
      {/* 正文不再自带滚动容器：Modal 内容区已是唯一竖向滚动区，
          这里再套一层会出现两条竖向滚动条（报告越长越明显） */}
      <div className="space-y-4">
        {/* 元数据 */}
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-ink-muted">
          <span>{report.code}</span>
          <span>评估时点 {report.as_of}</span>
          <span>数据日期 {report.data_date ?? '—'}</span>
          <span>耗时 {formatValuationDuration(report.analysis_duration_seconds)}</span>
          <span>Skill {report.skill_version ? `v${report.skill_version}` : '版本未知'}</span>
          <span>证据 {report.evidence.length} 条</span>
          <SessionDownloadButton runId={report.run_id} download={dividendApi.downloadValuationSession} />
        </div>
        {versionMismatch && (
          <p className="text-sm text-amber-700">当前已部署 Skill v{currentSkillVersion}，与报告版本不同，建议重新评估。</p>
        )}

        {/* 非 ready：原因与缺口，不渲染任何价格 */}
        {!isReady && (
          <div className="rounded-lg border border-rule bg-paper-tint p-4 space-y-2">
            <p className="font-medium text-ink">
              {VALUATION_STATUS_LABEL[report.status]} · 未生成价格挡位
            </p>
            <p className="text-sm text-ink-muted">{report.summary}</p>
            {report.data_gaps.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-ink-muted mb-1">待补材料 / 缺口</p>
                <ul className="list-disc list-inside text-sm text-ink">
                  {report.data_gaps.map((gap, i) => <li key={i}>{gap}</li>)}
                </ul>
              </div>
            )}
            <p className="text-xs text-ink-muted">收藏继续保留，当前监控配置不受影响。补齐关键材料后可重新评估。</p>
          </div>
        )}

        {/* ready：四份价格 + 旧值对比 */}
        {isReady && report.levels && (
          <div className="rounded-lg border border-rule p-4">
            <p className="text-xs font-semibold text-ink-muted mb-2">
              {hasOld ? '新评估挡位（划线为当前生效值）' : '挡位价格（元）'}
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {VALUATION_LEVEL_KEYS.map(key => {
                const point = report.levels?.[key];
                if (!point) return null;
                const old = effectiveLevels?.[key]?.price;
                const changed = old != null && Math.abs(old - point.price) > 1e-9;
                return (
                  <div key={key} className="rounded border border-rule bg-paper-deep px-2.5 py-2">
                    <div className="flex items-center gap-1.5 text-xs text-ink-muted">
                      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: LEVEL_META[key].color }} />
                      {VALUATION_LEVEL_LABEL[key]}
                    </div>
                    <div className="font-mono text-lg font-semibold text-ink tabular-nums">
                      ¥{point.price.toFixed(2)}
                      {changed && old != null && (
                        <span className="ml-1.5 text-xs font-normal text-ink-muted line-through">
                          ¥{old.toFixed(2)}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] font-mono text-ink-muted tabular-nums">
                      PE {point.pe != null ? point.pe.toFixed(1) : '—'} · PB {point.pb != null ? point.pb.toFixed(2) : '—'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 摘要 */}
        <div>
          <h3 className="text-sm font-semibold text-ink mb-1">摘要</h3>
          <p className="text-sm text-ink whitespace-pre-wrap">{report.summary}</p>
        </div>

        {/* 风险 / 复核条件 */}
        {report.risks.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-ink mb-1">风险</h3>
            <ul className="list-disc list-inside text-sm text-ink space-y-0.5">
              {report.risks.map((risk, i) => <li key={i}>{risk}</li>)}
            </ul>
          </div>
        )}
        {report.invalidation_conditions.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-ink mb-1">触发复核的条件</h3>
            <ul className="list-disc list-inside text-sm text-ink space-y-0.5">
              {report.invalidation_conditions.map((cond, i) => <li key={i}>{cond}</li>)}
            </ul>
          </div>
        )}

        {/* 研究正文（skill report_md） */}
        <div className="border-t border-rule pt-3">
          <h3 className="text-sm font-semibold text-ink mb-2">估值依据</h3>
          {/* md-body/quality-reader-md 提供表格边框、断词修正与标题排版；缺了表格会裸渲染塌缩 */}
          <div className="quality-reader-content md-body quality-reader-md text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={markdownComponents}>
              {report.report_md}
            </ReactMarkdown>
          </div>
        </div>

        {/* 证据来源 */}
        {report.evidence.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-accent">研究材料与来源（{report.evidence.length}）</summary>
            <ul className="mt-2 space-y-1.5">
              {report.evidence.map((ev, i) => (
                <li key={i} className="text-xs text-ink-muted">
                  <span className="text-ink">{String(ev.title ?? ev.id ?? '—')}</span>
                  {' · '}
                  {String(ev.kind ?? '')}
                  {ev.period ? ` · 期间 ${String(ev.period)}` : ''}
                  {ev.verification ? ` · ${String(ev.verification)}` : ''}
                  {ev.origin ? <span className="block break-all">{String(ev.origin)}</span> : null}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </Modal>
  );
}
