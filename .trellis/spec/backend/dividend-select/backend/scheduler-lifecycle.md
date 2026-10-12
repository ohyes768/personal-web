# Scheduler Lifecycle

APScheduler 3.x `AsyncIOScheduler.shutdown` accepts only `wait`; it does not
accept a timeout. Its `AsyncIOExecutor.shutdown` cancels pending futures even
when `wait=True`. Removing the timeout argument alone does not implement drain.

`SchedulerManager` must pause admission, reject manual triggers and resume
requests, and track wrapper tasks through history persistence. Wait for those
tasks with a bounded `asyncio.wait` before calling `shutdown(wait=False)`.
Await `EVENT_SCHEDULER_SHUTDOWN`, since AsyncIOScheduler schedules shutdown onto
the event loop. Queued wrappers must not begin a new target after closing starts.

Cancellation is cooperative. Cancelling the scheduler's HTTP client does not
guarantee cancellation of the server's refresh operation or worker threads.
Uvicorn shutdown also stops accepting new self-call connections, so this drain
contract covers already submitted scheduler wrappers, not arbitrary refreshes.

Regression tests: `tests/test_scheduler_shutdown.py` uses a real scheduler and
isolated targets to exercise idle stop, successful drain and history persistence,
deadline cancellation, immediate stop, admission rejection, restart, and repeated
shutdown. Run alongside scheduler jobs and timezone tests.

The current deployment does not involve n8n. No dual-run migration gate applies.
