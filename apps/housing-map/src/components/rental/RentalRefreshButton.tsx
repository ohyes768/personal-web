'use client';

import type { RentalRefreshJob } from '../../lib/rental-types';
import { rentalRefreshProgressText, rentalRefreshTerminalNote } from '../../lib/rental-dashboard';
import { useRentalRefresh } from '../../lib/use-rental-refresh';

interface RentalRefreshControlProps {
  job: RentalRefreshJob | null;
  running: boolean;
  actionError: string | null;
  start: () => void;
  cancel: () => void;
  onManageSources?: () => void;
}

/**
 * "更新租金"按钮 + 任务状态展示（design.md "Web refresh"）。
 * 范围固定为全部已核验映射小区（title 明确文案）；进度只显示"已处理小区/总小区"，
 * 不假装百分比。展示与 hook 分离，便于 node:test 直接渲染各状态。
 */
export function RentalRefreshControl({ job, running, actionError, start, cancel, onManageSources }: RentalRefreshControlProps) {
  const progress = rentalRefreshProgressText(running ? job : null);
  const terminalNote = rentalRefreshTerminalNote(running ? null : job);
  const terminalFailed = Boolean(job?.result && job.result.failed_count > 0);
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
      {running ? (
        <>
          <span role="status" style={{ fontSize: '12px', color: 'var(--accent-warm)' }}>{progress}</span>
          <button type="button" className="btn btn-secondary" style={{ padding: '4px 12px', fontSize: '12px' }} onClick={cancel}>
            取消
          </button>
        </>
      ) : (
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: '4px 12px', fontSize: '12px' }}
          onClick={start}
          title="检查滨江住宅小区来源并更新租金，拿不准的可单选或跳过"
        >
          更新租金
        </button>
      )}
      {terminalNote && (
        <span style={{ fontSize: '12px', color: terminalFailed ? 'var(--price-up)' : 'var(--text-muted)' }}>
          {terminalNote}
        </span>
      )}
      {!running && job?.association && job.association.pending + job.association.missing + job.association.failed > 0 && onManageSources && (
        <button type="button" className="btn btn-secondary" onClick={onManageSources}>处理租金来源</button>
      )}
      {actionError === '还没有关联租金来源，请先选择小区并确认来源' && onManageSources && (
        <button type="button" className="btn btn-secondary" onClick={onManageSources}>查找租金来源</button>
      )}
      {actionError && (
        <span role="alert" style={{ fontSize: '12px', color: 'var(--price-up)' }}>{actionError}</span>
      )}
    </span>
  );
}

/**
 * 容器：内部持有 useRentalRefresh 实例。
 * 看板与小区详情标签各自渲染实例，任务状态由后端 job 持久化，挂载时 GET 恢复；
 * onSettled（任务终态）由调用方重拉各自数据。
 */
export function RentalRefreshButton({ onSettled, onManageSources }: { onSettled?: () => void; onManageSources?: () => void }) {
  const refresh = useRentalRefresh(onSettled);
  return (
    <RentalRefreshControl
      job={refresh.job}
      running={refresh.running}
      actionError={refresh.actionError}
      start={refresh.start}
      cancel={refresh.cancel}
      onManageSources={onManageSources}
    />
  );
}
