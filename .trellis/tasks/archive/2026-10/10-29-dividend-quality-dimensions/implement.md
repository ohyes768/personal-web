# Execution plan

1. Record expanded requirements and activate the reviewed task. Read backend contracts and relevant UI/skill scripts.
2. Write failing backend tests for version parsing/persistence, configured manifest lookup, expected-version checking and idempotency separation. Add browser tests for five-column mapping, null dimensions and current/old/unknown versions.
3. Implement backend version metadata and frontend dimensions/version/report presentation; preserve queue changes and existing unrelated edits.
4. Update skill finalizer/validator/output docs with a deterministic version stamp and 4.3.0 contract; verify with its existing arithmetic and validator tests plus new version assertions. Use scoped filesystem escalation for the external skills repository.
5. Run quality service/API/Hermes tests, TypeScript and screening Playwright regressions; review rendered table. Update executable specs and task verification evidence. Do not deploy or commit.

## No-stars follow-up

1. Add failing skill tests for forbidden aggregate prose and retained JSON arithmetic, plus a browser regression with a historical stars/boundary record.
2. Remove the modal star/boundary header. Update the actual skill finalizer, validator and report requirements; bump to 4.4.0.
3. Run all skill tests, TypeScript and screening regressions. Update task/spec evidence, preserve other ongoing queue-control edits, and leave publication/deployment for the release step.
