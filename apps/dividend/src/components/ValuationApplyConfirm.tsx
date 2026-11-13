/**
 * ValuationApplyConfirm — 应用四挡位前的紧凑确认卡
 *
 * 行内「应用」入口：把「查看报告」与「应用」拆成两个动作后，这里负责确认这一步。
 * 正文只放新旧四档对比（不重复报告正文），底部固定操作区放取消 / 确认应用。
 * 没有生效挡位（首次应用）时只列新价，说明文案随之切换。
 */
'use client';

import { Modal } from './shared-ui/Modal';
import {
  VALUATION_LEVEL_KEYS,
  VALUATION_LEVEL_LABEL,
  VALUATION_ZONE_LABEL,
  reportLevelsToAlertLevels,
  resolveValuationZone,
  type ValuationReportRecord,
} from '@/lib/valuation';
import type { AlertLevels } from '@/lib/types';

export interface ValuationApplyConfirmProps {
  isOpen: boolean;
  onClose: () => void;
  report: ValuationReportRecord | null;
  /** 当前生效挡位（对比用；为空表示首次应用） */
  effectiveLevels: AlertLevels | null;
  /** 现价（判断应用后落在哪一区、会不会触发提醒） */
  currentPrice: number | null;
  applyPending?: boolean;
  applyError?: string;
  onApply: (report: ValuationReportRecord) => Promise<void> | void;
}

interface CompareRow {
  key: string;
  next: number | null;
  old: number | null;
  delta: number | null;
  pe: number | null;
  pb: number | null;
}

export function ValuationApplyConfirm({
  isOpen, onClose, report, effectiveLevels, currentPrice, applyPending = false, applyError = '', onApply,
}: ValuationApplyConfirmProps) {
  if (!report) return null;

  const rows: CompareRow[] = VALUATION_LEVEL_KEYS.map(key => {
    const point = report.levels?.[key];
    const next = point?.price ?? null;
    const old = effectiveLevels?.[key]?.price ?? null;
    const delta = next != null && old != null && old > 0 ? ((next - old) / old) * 100 : null;
    return { key, next, old, delta, pe: point?.pe ?? null, pb: point?.pb ?? null };
  }).filter(r => r.next != null);
  const hasOld = rows.some(r => r.old != null);

  // 应用后现价落在哪一区、会不会立刻触发提醒（口径与后端告警一致）
  const newZone = resolveValuationZone(reportLevelsToAlertLevels(report.levels), currentPrice);
  const oldZone = resolveValuationZone(effectiveLevels, currentPrice);
  const zoneText = newZone.zone && currentPrice != null ? (
    <div className={`rounded-lg border px-3 py-2 ${newZone.willTrigger ? 'border-amber-200 bg-amber-50' : 'border-rule bg-paper-tint'}`}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
        <span className="font-mono font-semibold tabular-nums text-ink">现价 ¥{currentPrice.toFixed(2)}</span>
        {oldZone.zone ? (
          <span className="text-ink-muted">
            旧挡位在 {VALUATION_ZONE_LABEL[oldZone.zone]}（{oldZone.willTrigger ? `触发${oldZone.hitLabel}` : '不触发提醒'}）
            {' → '}
            新挡位在 {VALUATION_ZONE_LABEL[newZone.zone]}
          </span>
        ) : (
          <span className="text-ink-muted">应用后落在 {VALUATION_ZONE_LABEL[newZone.zone]}</span>
        )}
      </div>
      <p className={`mt-1 text-xs ${newZone.willTrigger ? 'text-amber-700' : 'text-ink-muted'}`}>
        {newZone.willTrigger
          ? `应用后下一次价格刷新会推送「${newZone.hitLabel}」钉钉提醒（距该档位线 ${newZone.distancePct != null ? (newZone.distancePct >= 0 ? '+' : '') + newZone.distancePct.toFixed(1) : '—'}%）`
          : '应用后不会触发提醒'}
      </p>
    </div>
  ) : null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`确认应用挡位 · ${report.name}`}
      size="md"
      footer={(
        <div>
          {applyError && <p role="alert" className="mb-2 text-sm text-red-600">{applyError}</p>}
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              className="rounded border border-rule-strong px-3 py-1.5 text-sm text-ink hover:bg-paper-tint"
              onClick={onClose}
            >
              取消
            </button>
            <button
              type="button"
              disabled={applyPending}
              data-testid="valuation-confirm-apply-button"
              className="rounded bg-accent px-3.5 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              onClick={() => void onApply(report)}
            >
              {applyPending ? '应用中…' : hasOld ? '确认替换挡位' : '确认应用'}
            </button>
          </div>
        </div>
      )}
    >
      <div className="space-y-3">
        <p className="text-sm text-ink-muted">
          {hasOld
            ? '应用后用新挡位覆盖当前生效挡位，并开启价格提醒；旧挡位不再生效。'
            : '应用后保存四条价格线，并开启价格提醒。'}
        </p>

        {zoneText}

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rule text-left text-xs text-ink-muted">
              <th className="py-1.5 font-medium">档位</th>
              <th className="py-1.5 text-right font-medium">新价（元）</th>
              <th className="py-1.5 text-right font-medium">当前生效（元）</th>
              <th className="py-1.5 text-right font-medium">变化</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.key} className="border-b border-rule/60 last:border-b-0">
                <td className="py-2 text-ink">{VALUATION_LEVEL_LABEL[r.key as keyof typeof VALUATION_LEVEL_LABEL]}</td>
                <td className="py-2 text-right">
                  <div className="font-mono font-semibold tabular-nums text-ink">¥{(r.next as number).toFixed(2)}</div>
                  {(r.pe != null || r.pb != null) && (
                    <div className="text-[10px] font-mono tabular-nums text-ink-muted">
                      PE {r.pe != null ? r.pe.toFixed(1) : '—'} · PB {r.pb != null ? r.pb.toFixed(2) : '—'}
                    </div>
                  )}
                </td>
                <td className="py-2 text-right font-mono tabular-nums text-ink-muted">
                  {r.old != null ? `¥${r.old.toFixed(2)}` : '—'}
                </td>
                <td className="py-2 text-right font-mono tabular-nums text-ink">
                  {r.delta != null ? `${r.delta >= 0 ? '+' : ''}${r.delta.toFixed(1)}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="text-xs text-ink-muted">要看估值依据请点「查看报告」，确认卡不重复报告正文。</p>
      </div>
    </Modal>
  );
}
