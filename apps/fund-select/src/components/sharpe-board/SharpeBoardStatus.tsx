/**
 * 榜单数据状态条 + 空态卡（R6/R9：失败、样本未更新、stale、成功空榜、
 * 展示无匹配、首次无数据各自独立呈现，不互相冒充）
 */
'use client';

import {
  formatBoardTime,
  type SharpeBoardAttempt,
  type SharpeBoardPhase,
  type SharpeBoardResponse,
} from '@/lib/sharpe-board';

/** 顶部状态条：最新成功榜单 + 最新尝试（失败 / 样本未更新）+ stale 提示 */
export function SharpeBoardStatusBar({ data }: { data: SharpeBoardResponse }) {
  const attempt: SharpeBoardAttempt | null = data.latest_attempt;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 bg-paper-card rounded-lg border border-rule text-xs text-ink-muted">
        <span>
          最新成功榜单：
          {data.latest_published_week !== null ? (
            <span className="tnum font-medium text-ink-strong">{data.latest_published_week}</span>
          ) : (
            <span>尚无</span>
          )}
        </span>
        {attempt && (
          <span>
            最近一次执行：
            <span className="tnum">{formatBoardTime(attempt.started_at)}</span>
            {' · '}
            <span className={attemptStatusClass(attempt.status)}>{attemptStatusText(attempt.status)}</span>
            {attempt.status === 'complete' && ` · 入选 ${attempt.selected_count} 只`}
            {attempt.trigger === 'manual' && ' · 手动'}
          </span>
        )}
        {data.stale && data.latest_published_week !== null && (
          <span className="text-accent">当前周尚未发布榜单，以上为旧榜日期（不冒充本周）</span>
        )}
      </div>

      {attempt !== null && attempt.status === 'failed' && attempt.errors.length > 0 && (
        <div role="alert" className="px-3 py-2 rounded-lg bg-down-tint text-xs leading-5 text-down">
          最近一次采集失败（{attempt.week_start} 周），该周不发榜、不重复计次：{attempt.errors.slice(0, 3).join('；')}
          {attempt.errors.length > 3 && `（另 ${attempt.errors.length - 3} 条）`}
        </div>
      )}
      {attempt !== null && attempt.status === 'skipped_no_new_data' && (
        <div role="status" className="px-3 py-2 rounded-lg bg-paper-tint text-xs leading-5 text-ink-muted">
          最近一次执行风险样本无更新，未发布新榜（已有榜单与历史保留，不重复抄旧值）。
        </div>
      )}
    </div>
  );
}

function attemptStatusText(status: string): string {
  if (status === 'complete') return '成功';
  if (status === 'failed') return '失败';
  if (status === 'skipped_no_new_data') return '样本未更新';
  return status;
}

function attemptStatusClass(status: string): string {
  if (status === 'complete') return 'text-up font-medium';
  if (status === 'failed') return 'text-down font-medium';
  return 'text-accent font-medium';
}

interface EmptyCardProps {
  phase: Extract<SharpeBoardPhase, 'no-data' | 'empty-board' | 'no-match'>;
  data: SharpeBoardResponse;
  onClearFilters: () => void;
}

/** 主区域空态卡（请求失败由页面单独渲染，含重试按钮） */
export function SharpeBoardEmptyCard({ phase, data, onClearFilters }: EmptyCardProps) {
  if (phase === 'no-data') {
    return (
      <div className="p-12 text-center text-ink-muted">
        <p className="font-medium text-ink-strong mb-2">榜单尚未开始记录</p>
        <p className="text-sm leading-6">
          每周六自动采集股基后发布当周入选名单；首次成功发布前这里没有历史可看。
          可通过右上角齿轮「立即执行」补跑本周（不倒填过往周）。
        </p>
      </div>
    );
  }
  if (phase === 'empty-board') {
    const completeEmpty =
      data.latest_attempt !== null
      && data.latest_attempt.status === 'complete'
      && data.latest_attempt.selected_count === 0;
    return (
      <div className="p-12 text-center text-ink-muted">
        <p className="font-medium text-ink-strong mb-2">
          {completeEmpty ? '最新一周成功发布：无基金符合入选条件（有效空榜）' : '暂无在榜记录'}
        </p>
        <p className="text-sm leading-6">
          {completeEmpty
            ? '空榜是有效结果：当周采集成功但零入选，不沿用旧值、不虚构数据点。'
            : '历史周次尚未成功发布过榜单（全部失败或未运行）；失败详情见上方状态条，可同周重试。'}
        </p>
      </div>
    );
  }
  return (
    <div className="p-12 text-center text-ink-muted">
      <p className="font-medium text-ink-strong mb-2">当前筛选条件下无匹配基金</p>
      <p className="text-sm leading-6">
        展示筛选只改变呈现，不改记录与历史数据；累计周数仍按全历史计算。
      </p>
      <button
        type="button"
        onClick={onClearFilters}
        className="mt-3 px-3 py-1.5 rounded-lg bg-paper-deep text-sm text-ink-muted hover:bg-info-tint hover:text-info transition-colors"
      >
        清除展示筛选
      </button>
    </div>
  );
}
