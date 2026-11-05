'use client';

import {
  refreshPhaseText,
  type RefreshJobView,
} from '../../lib/price-freshness';

// 顶部价格刷新入口 (R3/R5): 两个按钮共用任务互斥。
// - 「刷新已收录」: 后端资格函数决定范围, 不受页面搜索/筛选影响;
// - 「补齐价格（N）」: N 为缺价小区去重数, N=0 时禁用 (没有可补齐目标);
// - 运行中显示进度与停止; 终态显示四类统计 + 跳过/保留旧价 + 警告。
export default function PriceRefreshControls({
  job,
  eligible,
  missing,
  notice,
  onRefresh,
  onStop,
}: {
  job: RefreshJobView | null;
  eligible: number | null;
  missing: number | null;
  notice: string | null;
  onRefresh: (mode: 'all' | 'missing') => void;
  onStop: () => void;
}) {
  const running = job?.running === true;
  const phaseText = job ? refreshPhaseText(job) : null;
  const warnings = job?.result?.warnings ?? [];
  const resultError = !running && job?.phase === 'error' ? (job.error ?? '刷新失败') : null;

  return (
    <div className="price-refresh-controls">
      <div className="price-refresh-buttons">
        {running ? (
          <>
            <span className="price-refresh-progress" role="status">
              {phaseText}
            </span>
            <button className="btn btn-secondary" onClick={onStop}>⏹ 停止</button>
          </>
        ) : (
          <>
            <button
              className="btn btn-secondary"
              style={{ whiteSpace: 'nowrap' }}
              onClick={() => onRefresh('all')}
              title={`按后端资格刷新全部已收录小区（当前 ${eligible ?? '…'} 个可采集）。
采集范围由服务端资格函数决定，不受页面搜索与筛选影响。`}
            >
              🔄 刷新已收录
            </button>
            <button
              className="btn btn-secondary"
              style={{ whiteSpace: 'nowrap' }}
              disabled={missing === 0}
              onClick={() => onRefresh('missing')}
              title={missing === 0
                ? '所有已收录小区都有当前可用价格（签约或挂牌其一即可），无需补齐'
                : `只刷新两种当前可用价格都没有的已收录小区（当前 ${missing ?? '…'} 个缺价）。
缺其中一种不算缺价；超过30天未更新但仍有可用价格不算缺价。
采集范围由服务端资格函数决定，不受页面搜索与筛选影响；启动时服务端会重新计算目标。`}
            >
              {missing == null ? '补齐价格' : `补齐价格（${missing}）`}
            </button>
          </>
        )}
      </div>
      {phaseText && !running && (
        <span className="price-refresh-result" role="status" title={warnings.join('\n') || undefined}>
          {phaseText}
        </span>
      )}
      {warnings.length > 0 && (
        <span className="price-refresh-warn" title={warnings.join('\n')}>
          ⚠ {warnings.length} 条警告
        </span>
      )}
      {resultError && <span className="price-refresh-error" role="alert">{resultError}</span>}
      {notice && !running && <span className="price-refresh-error" role="alert">{notice}</span>}
    </div>
  );
}
