import type { CatalogRow } from './DirectoryFlowWorkspace';

export type CatalogReviewKind = 'reopen-review' | 'complete-review';

/** Lists and details expose the same re-review transitions. */
export function CatalogReviewAction({ row, busy, action }: {
  row: CatalogRow; busy: boolean; action: (kind: CatalogReviewKind, row: CatalogRow) => void;
}) {
  if (!row.collection_pipeline_version || row.source_record_id || row.deleted || row.merged_to || !row.admission?.revision) return null;
  const kind: CatalogReviewKind | null = row.workflow_state === 'pending' && row.admission.review_requested
    ? 'complete-review' : row.workflow_state === 'admitted' || row.workflow_state === 'excluded' ? 'reopen-review' : null;
  if (!kind) return null;
  return <button className="btn btn-secondary" disabled={busy}
    title={kind === 'reopen-review' ? '移到待处理，保留资料，核对后再决定是否收录' : '按当前资料重新判断，符合条件才会收录'}
    onClick={() => action(kind, row)}>{kind === 'reopen-review' ? '重新审核' : '完成审核'}</button>;
}
