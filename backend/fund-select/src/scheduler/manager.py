"""Four independent weekly schedules, with one shared collection queue."""
import asyncio
import json
from collections import deque
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.config import DATA_DIR, PROJECT_ROOT
from src.utils.logger import setup_logger

logger = setup_logger('fund-select.scheduler')
SCHEDULER_CONFIG = PROJECT_ROOT / 'src' / 'scheduler' / 'scheduler.json'
LEGACY_JOB_ID = 'weekly_fund_refresh'


class SchedulerManager:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.scheduler = AsyncIOScheduler(timezone='Asia/Shanghai')
        self.state_dir = state_dir if state_dir is not None else DATA_DIR / 'scheduler'
        self.history_path = self.state_dir / 'weekly_refresh.jsonl'
        self.settings_path = self.state_dir / 'settings.json'
        self.jobs_meta: dict[str, dict] = {}
        self._running: set[str] = set()
        self._current_runs: dict[str, dict] = {}
        self._last_records: dict[str, dict] = {}
        self._snapshot_lock = Lock()
        self._execution_lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task] = set()

    def start(self, app) -> None:
        config = json.loads(SCHEDULER_CONFIG.read_text(encoding='utf-8'))
        settings = json.loads(self.settings_path.read_text(encoding='utf-8')) if self.settings_path.exists() else {}
        for spec in config['jobs']:
            enabled = settings.get(spec['id'], settings.get(LEGACY_JOB_ID, spec.get('enabled', True)))
            spec = {**spec, 'enabled': enabled}
            if spec['target'] != 'refresh_tab':
                raise ValueError(f"未知定时任务 target: {spec['target']}")
            self.jobs_meta[spec['id']] = spec
            self.scheduler.add_job(
                self._run_scheduled,
                CronTrigger.from_crontab(spec['cron'], timezone='Asia/Shanghai'),
                args=[spec['id']], id=spec['id'], name=spec['name'], replace_existing=True,
                max_instances=1, coalesce=True, misfire_grace_time=3600,
            )
            if not enabled:
                self.scheduler.pause_job(spec['id'])
            logger.info('注册定时任务 %s @ %s Asia/Shanghai', spec['id'], spec['cron'])
        self.scheduler.start()

    def _require_job(self, job_id: str) -> dict:
        if job_id not in self.jobs_meta:
            raise KeyError(job_id)
        return self.jobs_meta[job_id]

    async def _run_scheduled(self, job_id: str) -> None:
        self._require_job(job_id)
        if job_id in self._running:
            logger.info('任务已在运行或排队，跳过重复调度 %s', job_id)
            return
        self._reserve(job_id, 'scheduled')
        await self._execute_reserved(job_id)

    def _reserve(self, job_id: str, trigger: str) -> None:
        from src.scheduler.weekly_refresh import _now
        self._running.add(job_id)
        self._update_snapshot(job_id, {'job_id': job_id, 'run_id': str(uuid4()), 'trigger': trigger,
                                       'start': _now(), 'status': 'queued', 'items': []})

    def _update_snapshot(self, job_id: str, record: dict) -> None:
        with self._snapshot_lock:
            self._current_runs[job_id] = deepcopy(record)

    async def _execute_reserved(self, job_id: str) -> None:
        from src.scheduler.weekly_refresh import _now, refresh_tab_sync
        try:
            async with self._execution_lock:
                with self._snapshot_lock:
                    initial = deepcopy(self._current_runs[job_id])
                self._update_snapshot(job_id, {**initial, 'status': 'running', 'start': _now()})
                result = await asyncio.to_thread(
                    refresh_tab_sync, tab=self.jobs_meta[job_id]['tab'], job_id=job_id,
                    history_path=self.history_path, trigger=initial['trigger'], run_id=initial['run_id'],
                    on_progress=lambda record: self._update_snapshot(job_id, record),
                )
                self._last_records[job_id] = result
        except Exception as exc:
            with self._snapshot_lock:
                self._last_records[job_id] = {**self._current_runs[job_id], 'status': 'failed',
                                              'end': _now(), 'error': str(exc)}
            logger.exception('任务刷新失败 %s', job_id)
        finally:
            self._running.discard(job_id)

    def list_jobs(self) -> list[dict]:
        result = []
        for job_id, spec in self.jobs_meta.items():
            job = self.scheduler.get_job(job_id)
            next_run = getattr(job, 'next_run_time', None)
            if spec['enabled'] and job is not None and not hasattr(job, 'next_run_time'):
                from src.scheduler.weekly_refresh import TIMEZONE
                next_run = job.trigger.get_next_fire_time(None, datetime.now(TIMEZONE))
            runs = self.get_job_runs(job_id, 1)
            running = job_id in self._running
            with self._snapshot_lock:
                current = deepcopy(self._current_runs.get(job_id)) if running else None
            result.append({**spec, 'timezone': 'Asia/Shanghai', 'running': running,
                           'next_run_time': next_run.isoformat() if next_run else None,
                           'current_run': current, 'last_run': self._last_records.get(job_id) or (runs[0] if runs else None)})
        return result

    def _save_settings(self, settings: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(settings, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.settings_path)

    def set_enabled(self, job_id: str, enabled: bool) -> dict:
        spec = self._require_job(job_id)
        self._save_settings({key: enabled if key == job_id else value['enabled'] for key, value in self.jobs_meta.items()})
        if enabled:
            self.scheduler.resume_job(job_id)
        else:
            self.scheduler.pause_job(job_id)
        spec['enabled'] = enabled
        return next(job for job in self.list_jobs() if job['id'] == job_id)

    async def trigger_now(self, job_id: str) -> dict:
        self._require_job(job_id)
        if job_id in self._running:
            raise ValueError('该任务正在运行或排队，请等待本轮结束')
        self._reserve(job_id, 'manual')
        task = asyncio.create_task(self._execute_reserved(job_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return {'status': 'queued', 'job_id': job_id}

    def get_job_runs(self, job_id: str, limit: int = 20) -> list[dict]:
        spec = self._require_job(job_id)
        if not self.history_path.exists():
            return []
        records: deque = deque(maxlen=limit)
        with self.history_path.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get('job_id') == job_id:
                    records.append(record)
                elif record.get('job_id') in (None, LEGACY_JOB_ID):
                    item = next((item for item in record.get('items', []) if item.get('tab') == spec['tab']), None)
                    if item:
                        projected = {**record, 'job_id': job_id, 'status': item['status'], 'items': [item],
                                     'start': item.get('start', record.get('start')), 'end': item.get('end', record.get('end'))}
                        projected.pop('error', None)
                        records.append(projected)
        return list(reversed(records))

    async def shutdown(self, wait: bool = False) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
