# Queue dispatch follow-up — 2026-11-02

User authorized fixing the missed wake-up and changing production concurrency to 1.

- Root cause: appending to an active job persisted new admissions but did not
  notify the dispatcher's Condition. With spare slots, it remained asleep until
  a running item finished. Production was configured for four concurrent runs.
- Change: notify only after successful durable append, under the same lock;
  change application and NAS Compose concurrency defaults to 1.
- Regression: hold the first fake Hermes run open, observe the dispatcher waiting,
  append another item with a free slot, and require it to start before releasing
  the first. Existing FIFO/concurrency/cancel tests cover occupied slots.
- Final deployment scope: user requested commit and push only and will deploy.
  Backend image build and isolated smoke check passed. No deployment waiter was
  started and the running container was never recreated. Remote source/Compose
  preparation was restored to its original state so the user's pull stays clean.
  On deployment, allow the existing two analyses to finish before restarting;
  the Compose default is 1 unless explicitly overridden by the environment.
- Initial regression run: two expected failures (default was 4; appended work did
  not wake the dispatcher). Full suite exposed an existing cancellation-test
  race: running state is set before remote submission, so the test now waits for
  its first fake upstream poll before requesting cancellation.
- Final checks: 85 tests passed across test_quality_service.py, test_quality_api.py,
  test_refresh_jobs.py and test_hermes_client.py; scoped git diff --check passed.
  The local interpreter emits an existing requests dependency-version warning.
