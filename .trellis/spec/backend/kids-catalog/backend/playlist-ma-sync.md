# Generation metadata and MA sync contract

Scope: src/collection_metadata.py, src/device_collections.py, src/ma_sync.py, src/music_assistant.py, app/generation-progress.ts and device-playlist.tsx.

- generation.integration is a backward-compatible JSON column: phase, tags_updated, metadata_errors, device_published, ma.status/message. Legacy DBs migrate on construction; snapshot schema and by-number endpoints do not change.
- Stages: tagging → publish compatible device snapshot (generation still running) → MA sync/verification → finished. MA failures are separate from device publication; done alone never means MA ready.
- Metadata only for selected, confirmed current downloads. Never silently confirm arbitrary manifest drift. Preserve existing tags; fill numbered missing tracks only; do not guess unnumbered order. Generic artist fallback is 哆咪音频, not a claim about authorship.
- No complete audio backups in this generation service (explicit user preference); temp copy/hash/readback/fsync/replace + per-file completion checkpoint. Original CLI remains backup-first.
- Crash recovery accepts only exact before/after stat + after SHA256 recorded by this service; differing filename sets or later touches must not be silently acknowledged.
- Lock order: catalog candidate_source guard → collections immediate transaction. Hold both around each file publication/checkpoint; never hold either for MA network calls. Final ready validation and done/ready commit stay in one catalog+collections transaction.
- All integration writes conditional on matching generation token and running status. A stale worker cannot overwrite the new task.
- MA selects available filesystem_local providers whose configured root contains KIDS_MA_MUSIC_ROOT; never hardcode a provider id. Use music/sync, then tasks/get until status success (partial_success is failure), bounded deadline.
- Ready requires exact normalized file paths, one matching target album, exact expanded album track count, and one target local file per returned track. Do not ignore foreign-only extra tracks. MA unavailable, no task, missing config, auth failure, timeout, stale files are explicit non-ready states.
- Credentials remain server-side; sanitized errors only. No browser tokens, credential logs or upstream error payloads.
- Validation: real MP3/M4A, partial-failure retries and audited recovery; skip/unselected/old API behavior; long collections; MA source/task/path mismatch/extra-track/deadline tests; final source-guard commit test; presenter tests + tsc + production build.
