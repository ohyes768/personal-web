# Active quality queue controls

Status: proposed planning. Product scope follows the user's simplified two-group design. Running cancellation depends on verifying the deployed Hermes API; no endpoint is assumed.

## UI

Reuse the existing toolbar button and Modal. Header shows running/queued counts only. Content contains running rows (name/code, elapsed time, cancel) and ordered waiting rows (name/code, position, move to front/up/down, cancel). Hide empty groups and show 暂无进行中的任务 when no active items remain. Remove terminal rows, aggregate job progress and retry controls from this modal; preserve reports and existing actions elsewhere.

Running cancellation shows 取消中… on the same row and disables repeated cancel while in flight. Keep the row and concurrency ownership until remote termination is established. Failed requests show a local error without implying termination; uncertain outcomes require continued status reconciliation. A completed run wins if it finished before cancellation, preserving its valid result. No confirmation dialog for single waiting cancellation; no bulk controls.

## Server ownership and action identity

Extend QualityService under its existing Condition lock. Each admission already has attempt_id: expose an opaque item identity and target mutations by that identity so a stale request cannot act on a later attempt for the same code. Include authoritative waiting order/position in quality snapshots. Frontend must use this order instead of re-sorting by queued_at. Keep timestamps unchanged on reorder.

Proposed local mutations (names to confirm against route conventions): POST /quality/queue/{item_id}/cancel and POST /quality/queue/{item_id}/move with action front/up/down. Return authoritative snapshot/revision or an explicit state conflict. Repeated cancellation is idempotent. Serialize dispatch, reorder and cancellation; stale/missing identities or an item that has already started cannot yield successful waiting-only reorder. Refresh the view after conflicts. Scope mutations to quality, leaving ordinary refresh ownership intact.

Reorder changes only pending items, preserving unaffected relative order; append remains at the tail. Waiting cancellation removes the exact attempt under the dispatch lock before it can submit to Hermes. Waiting ordering must match actual dispatch, including the item at a concurrency boundary: currently the dispatcher marks running before semaphore.acquire, so implementation must claim a real free slot before transitioning queued → running. Otherwise an unsent item can become impossible to reorder/cancel as waiting.

## Running cancellation

First verify the deployed Hermes cancellation method, response semantics and terminal confirmation. Store the run_id and cancellation intent against the exact attempt; cover intent arriving while submit_run has not yet returned. Do not hold the queue lock across network requests. Introduce cancelling/cancelled as distinct internal item states as needed; cancelling remains active and duplicate-protected until a real terminal result.

Do not release a slot, report cancellation success or hide the item merely because local polling stopped or a timeout occurred. Cancellation failure/uncertainty retains ownership and reconciliation. Guard final score publication against cancellation/completion races. Preserve the previous successful score when a later attempt is cancelled.

Rejoining after confirmed cancellation must not reuse a cancelled Hermes run through the existing stock/date/skill-version idempotency key. Use an attempt-aware generation policy for explicitly cancelled re-admissions while preserving safe retries of the same uncertain submit. Verify this against the upstream contract before implementation approval.

## Accounting, recovery and compatibility

Track cancellation separately from success/failure. Extend quality progress accounting so cancelled admissions resolve remaining exactly once, disappear from retry_codes unless a distinct later attempt needs retry, and let a fully drained job reach an honest terminal state. Determine quality-only job terminal mapping with focused tests; do not change m120/financial semantics. Keep compatibility for old job records missing cancellation fields.

Persist accepted order/cancellation changes before acknowledgement using existing atomic job storage patterns; persist no credentials. On page refresh the server snapshot is authoritative. Keep the existing service-restart interrupted/manual-retry behavior, without auto replay. Closing the modal stops its display timer only. Do not delete internal terminal metadata needed for race protection/accounting simply because the UI hides terminal records.

## Alternatives and rollout

Browser-only reordering cannot control dispatch and is rejected. Stopping polling cannot cancel Hermes work and is rejected. Server-owned mutations with confirmed remote cancellation are recommended. If upstream cannot cancel, mark running cancellation capability unavailable and report this implementation limitation; no simulated success.

Coordinate frontend/backend deployment for new actions and state fields. Drain analysis before rollback. This planning task does not authorize production deployment or changing the upstream Hermes service.
