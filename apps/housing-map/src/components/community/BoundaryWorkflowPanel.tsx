'use client';

import {
  BoundaryCandidate,
  BoundaryWorkflowState,
  boundaryAreaText,
  boundaryErrorText,
  boundaryFootnote,
  boundaryOriginLabel,
  boundaryPhaseLabel,
  boundaryReferenceSummary,
  isBoundaryJobActive,
} from '../../lib/boundary-workflow';

export interface BoundaryWorkflowActions {
  startEstimate: (options?: { regenerate?: boolean; refreshBuildings?: boolean }) => Promise<void>;
  applyCandidate: () => Promise<void>;
  rejectCandidate: () => Promise<void>;
  revert: () => Promise<void>;
}

export interface BoundaryPanelView {
  state: BoundaryWorkflowState | null;
  candidate: BoundaryCandidate | null;
  jobPhase: string | null;
  jobError: string | null;
  jobErrorCode: string | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
}

function statusText(state: BoundaryWorkflowState | null): { label: string; tone: 'ok' | 'warn' | 'muted' } {
  if (!state) return { label: '读取中', tone: 'muted' };
  if (state.override) return { label: '建筑估算 · 人工确认', tone: 'ok' };
  if (state.has_visible_boundary) return { label: '已有地块轮廓', tone: 'ok' };
  return { label: '暂无地块轮廓', tone: 'warn' };
}

function confirmedAtText(value: string | null): string {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('zh-CN', { hour12: false });
}

/** 「地块轮廓」tab 的摘要区: 状态 + 入口。 */
export function BoundaryWorkflowSection({
  view,
  actions,
  onPreview,
}: {
  view: BoundaryPanelView;
  actions: BoundaryWorkflowActions;
  onPreview: () => void;
}) {
  const { state, candidate, jobPhase, busy } = view;
  const status = statusText(state);
  const active = isBoundaryJobActive(jobPhase);
  const failure = view.error || (view.jobError ? boundaryErrorText(view.jobErrorCode, view.jobError) : '');

  return (
    <div className="boundary-section">
      <div className="boundary-status-row">
        <span className={`boundary-dot ${status.tone}`} aria-hidden="true" />
        <span className="boundary-status-text">{status.label}</span>
        {state?.override && (
          <span className="boundary-status-meta">{confirmedAtText(state.override.confirmed_at)}</span>
        )}
      </div>

      {active && (
        <p className="boundary-hint">
          {boundaryPhaseLabel(jobPhase)}中，完成后可以在这里查看候选。
        </p>
      )}

      {!active && failure && (
        <p className="boundary-error" role="alert">{failure}</p>
      )}

      {!state?.has_visible_boundary && !active && (
        <>
          <p className="boundary-hint">
            {candidate
              ? '已有候选轮廓，确认无误后应用到地图。'
              : failure
                ? '没有拿到建筑数据，可以稍后重试。'
                : '轮廓由开放街图数据估算，生成后需要人工确认范围是否合适。不是测绘或产权边界。'}
          </p>
          <div className="boundary-actions">
            {candidate ? (
              <button type="button" className="btn btn-primary" onClick={onPreview} disabled={busy}>
                查看候选
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={() => void actions.startEstimate()} disabled={busy}>
                {busy ? '正在发起…' : failure ? '重新生成轮廓' : '生成候选轮廓'}
              </button>
            )}
          </div>
        </>
      )}

      {state?.has_visible_boundary && state.override && (
        <div className="boundary-actions">
          <button type="button" className="btn btn-secondary" onClick={() => void actions.revert()} disabled={busy}>
            撤销本次应用
          </button>
        </div>
      )}
    </div>
  );
}

/** 候选预览: 在「地块轮廓」tab 内就地确认, 地图同步高亮候选范围。 */
export function BoundaryWorkflowPreview({
  view,
  actions,
  onBack,
  onLocate,
  showReferences,
  onToggleReferences,
}: {
  view: BoundaryPanelView;
  actions: BoundaryWorkflowActions;
  onBack: () => void;
  onLocate: () => void;
  showReferences: boolean;
  onToggleReferences: (next: boolean) => void;
}) {
  const { candidate, jobPhase, jobError, jobErrorCode, busy, error, loading } = view;
  const active = isBoundaryJobActive(jobPhase);

  return (
    <div className="boundary-preview">
      <div className="boundary-preview-head">
        <button type="button" className="boundary-back" onClick={onBack}>← 返回</button>
        <span className="boundary-status-text">候选轮廓确认</span>
      </div>

      {loading && <p className="boundary-hint">读取轮廓状态…</p>}
      {error && <p className="boundary-error" role="alert">{error}</p>}
      {jobError && <p className="boundary-error" role="alert">{boundaryErrorText(jobErrorCode, jobError)}</p>}

      {active && (
        <div className="boundary-progress">
          <span className="boundary-spinner" aria-hidden="true" />
          <span>{boundaryPhaseLabel(jobPhase)}中…</span>
        </div>
      )}

      {candidate && (
        <>
          <div className="boundary-facts">
            <div className="stat-cell">
              <div className="stat-label">估算面积</div>
              <div className="stat-value">{boundaryAreaText(candidate.area_ha)}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-label">参考面</div>
              <div className="stat-value">{candidate.building_faces + candidate.residential_faces}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-label">数据来源</div>
              <div className="stat-value">{boundaryOriginLabel(candidate)}</div>
            </div>
          </div>

          <p className="boundary-hint">{boundaryReferenceSummary(candidate)}</p>

          {candidate.warnings.length > 0 && (
            <ul className="boundary-warnings">
              {candidate.warnings.map(warning => <li key={warning}>{warning}</li>)}
            </ul>
          )}

          {candidate.stale && (
            <p className="boundary-error" role="alert">
              候选已过期：{candidate.stale_reasons.join('；')}，请重新生成。
            </p>
          )}

          <label className="boundary-toggle">
            <input
              type="checkbox"
              checked={showReferences}
              onChange={event => onToggleReferences(event.target.checked)}
            />
            显示参考建筑（{candidate.building_faces + candidate.residential_faces}）
          </label>

          <div className="boundary-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void actions.applyCandidate()}
              disabled={busy || !candidate.applicable}
            >
              应用此轮廓
            </button>
            <button type="button" className="btn btn-secondary" onClick={onLocate}>
              去核对定位
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void actions.rejectCandidate()}
              disabled={busy}
            >
              范围不合适
            </button>
          </div>

          <div className="boundary-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void actions.startEstimate({ regenerate: true })}
              disabled={busy}
            >
              重新生成
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void actions.startEstimate({ regenerate: true, refreshBuildings: true })}
              disabled={busy}
            >
              重新获取建筑
            </button>
          </div>
        </>
      )}

      {!candidate && !active && (
        <p className="boundary-hint">当前没有待确认的候选轮廓。</p>
      )}

      <p className="boundary-footnote">
        {boundaryFootnote(candidate)}
      </p>
    </div>
  );
}
