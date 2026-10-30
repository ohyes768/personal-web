# Hermes run cancellation

Checked: 2026-10-29. No live user run was created, stopped, or polled.

## Source

Authoritative schema: [Hermes API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server) (Nous Research hermes-agent), fetched 2026-10-29.

This workspace has no `HERMES_BASE_URL` or `HERMES_API_KEY` (no `backend/dividend-select/.env` / `.env.local`, and the shell session does not export them), so `GET /v1/capabilities` on the deployed profile was not called. The contract below is the published Runs API, not an invented route. An older deployment that does not implement it must fail the stop call; this backend must not treat that failure as a successful cancel.

## Method

`POST {base}/p/{profile}/v1/runs/{run_id}/stop`

Profile routing matches the existing submit/poll client: `/p/{HERMES_PROFILE}/v1/runs/{run_id}/stop`. Another profile's run id is `404`, not `403`.

`GET /v1/capabilities` advertises support as `features.run_stop: true`. The same document lists the route next to `events`, `approval`, and `resolve-unknown`.

## Payload and authentication

- Authentication: `Authorization: Bearer {API_SERVER_KEY}` (the same key as submit/poll; for `/p/{profile}/` it must be that profile's key).
- No request body is documented. A malformed control body is `400 invalid_params`.
- Do not send the create-run `Idempotency-Key` on stop. That header belongs to `POST /v1/runs`.

## Acceptance versus terminal confirmation

Acceptance and completion are different:

| Signal | Meaning |
| --- | --- |
| HTTP 2xx and `{"status": "stopping"}` | Stop was accepted. The agent is asked to halt at the next safe point. The worker is still running. |
| Poll `status: "stopping"` | Non-terminal. Keep the slot and the row. |
| Poll `status: "cancelled"` | Terminal confirmation. Runs polling and SSE agree on `cancelled`. |
| Poll `status: "completed"` | The turn finished before the stop took effect. Keep the output. Do not record a cancellation. |
| Poll `status: "failed"` or `"interrupted"` | Terminal failure, not a confirmed cancel. |
| Poll `status: "unknown"` | Non-terminal. `POST .../stop` returns `409 unknown_execution` and does not resolve it. Resolution is a different route (`resolve-unknown`) and is out of scope. |

`stopping` must not be treated as success, and stopping local polling or hitting the client timeout must not be treated as `cancelled`. Statuses are retained only briefly after a terminal state, so confirmation has to be observed by polling.

While the gateway is draining, non-terminal runs may also carry `shutdown_requested_at`. `status` stays `running` until the run ends `interrupted`. That field is not a cancel confirmation.

## Unsupported or non-confirming behavior

- There is no documented `DELETE /v1/runs/{id}` cancel. `DELETE /api/jobs/{job_id}` cancels a scheduled job's in-flight run and is a different resource; do not use it for a quality run.
- HTTP 503 `runtime_draining` or `storage_unavailable` (optional `Retry-After`) means the control was not applied.
- HTTP 409 is an ownership, generation, or identity refusal (`unknown_execution` for an unknown admission). It is not confirmation.
- HTTP 404 means the run is not visible to this profile.
- A client timeout, a dropped GET, or an expired SSE buffer does not stop the executor. The run remains visible to status polling and stop until the executor exits.

## Submit / cancel races

Stop requires a `run_id`. If the user cancels after the local item is running but `POST /v1/runs` has not returned, store the intent and call stop as soon as the `run_id` exists. Do not hold the local queue lock across that POST.

If the run reaches `completed` before the executor honors the stop, the completed output wins. A later `cancelled` poll is the only signal that the stop won.

## Idempotency after cancellation

`POST /v1/runs` with an `Idempotency-Key` reserves the key before work starts. An identical retry returns the original `run_id` with HTTP 202 and `Idempotency-Replayed: true`, including after the run has completed, failed, or been **cancelled**. The same key with a different JSON body is HTTP 409 `idempotency_key_conflict`. Keys are scoped to the profile and credential and kept for 24 hours after the last status update.

Consequence for quality ratings:

- A retry of the same uncertain submit (no `run_id` yet, or stop not confirmed) must reuse `quality-{code}-{data_date}-{skill_version}` so Hermes replays that admission instead of starting a second one.
- After a **confirmed** `cancelled` poll, the next admission of that stock must not reuse that key, or Hermes will replay the cancelled run for up to 24 hours. Append an attempt generation (`-c{n}`) only in that case.
- A waiting item cancelled before any `POST /v1/runs` never reserved a key, so the next admission keeps the unscoped key.

## Decision

Running cancellation is supported by the published Runs API. Implement `stop_run` plus poll-until-`cancelled`/`completed`. Surface HTTP and timeout failures on the row and keep the concurrency slot until a real terminal status. Do not simulate success when stop is refused or the deployment has no such route.
