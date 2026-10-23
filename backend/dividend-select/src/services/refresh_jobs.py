"""Single-process refresh ownership; worker threads never touch asyncio primitives."""
import asyncio
import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.utils.atomic_file import atomic_write
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
ACTIVE = {'queued', 'running'}


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


class RefreshJobManager:
    def __init__(self, directory: Path):
        self.directory = directory
        self._lock = threading.RLock()
        self._jobs = {}
        self._futures = {}
        self._last_save = {}
        self._closing = False
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='dividend-refresh')
        for path in sorted(directory.glob('*.json')):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job['status'] in ACTIVE:
                    job.update(status='interrupted', error='服务重启，刷新已中断，请手动重试', finished_at=now(), updated_at=now())
                    job['retry_codes'] = job['codes']
                    self._save(job)
                self._jobs[job['job_id']] = job
            except (ValueError, KeyError, OSError):
                logger.exception('无法恢复刷新任务 %s', path)
        self._prune()

    def _save(self, job):
        encoded = json.dumps(job, ensure_ascii=False, allow_nan=False)
        atomic_write(self.directory / f"{job['job_id']}.json", lambda p: p.write_text(encoded, encoding='utf-8'))
        self._last_save[job['job_id']] = time.monotonic()

    def _prune(self):
        for kind in ('m120', 'financial', 'quality'):
            jobs = sorted((j for j in self._jobs.values() if j['kind'] == kind), key=lambda j: j['created_at'], reverse=True)
            for job in jobs[20:]:
                if job['status'] not in ACTIVE:
                    (self.directory / f"{job['job_id']}.json").unlink(missing_ok=True)
                    self._jobs.pop(job['job_id'], None)
                    self._futures.pop(job['job_id'], None)
                    self._last_save.pop(job['job_id'], None)

    def get(self, job_id):
        with self._lock:
            return copy.deepcopy(self._jobs.get(job_id))

    def latest(self, kind):
        with self._lock:
            jobs = [j for j in self._jobs.values() if j['kind'] == kind]
            return copy.deepcopy(max(jobs, key=lambda j: j['created_at'])) if jobs else None

    def active(self, kind):
        with self._lock:
            for job in self._jobs.values():
                if job['kind'] == kind and job['status'] in ACTIVE:
                    return {**copy.deepcopy(job), 'reused': True}
        return None

    def submit(self, kind, codes, work, params=None):
        with self._lock:
            if self._closing:
                return None
            existing = self.active(kind)
            if existing:
                return existing
            codes = list(dict.fromkeys(codes))
            job = dict(job_id=uuid4().hex, kind=kind, status='queued', codes=codes,
                       params=params or {}, total=len(codes), processed=0, succeeded=0, failed=0,
                       remaining=len(codes), failed_codes=[], retry_codes=codes[:], error=None,
                       created_at=now(), updated_at=now(), started_at=None, finished_at=None,
                       message='已受理，等待后台刷新')
            self._save(job)  # Admission must be durable before work starts.
            self._jobs[job['job_id']] = job
            self._futures[job['job_id']] = self._executor.submit(self._run, job, work)
            self._prune()
            return {**copy.deepcopy(job), 'reused': False}

    def _run(self, job, work):
        seen = set()
        try:
            with self._lock:
                job.update(status='running', started_at=now(), updated_at=now())
                self._save(job)
            def progress(code, success):
                with self._lock:
                    if code in seen or code not in job['codes']:
                        raise ValueError('无效或重复的股票进度')
                    seen.add(code)
                    job['processed'] += 1
                    job['succeeded' if success else 'failed'] += 1
                    if not success:
                        job['failed_codes'].append(code)
                    job['remaining'] = job['total'] - job['processed']
                    job['retry_codes'] = [c for c in job['codes'] if c not in seen or c in job['failed_codes']]
                    job['updated_at'] = now()
                    if time.monotonic() - self._last_save[job['job_id']] >= 1:
                        self._save(job)
            work(progress)
            with self._lock:
                if job['remaining']:
                    job['error'] = '采集提前停止，仍有未处理股票（可能触发限流保护）'
                job['status'] = ('succeeded' if not job['failed'] and not job['remaining'] else
                                 'partial_failed' if job['succeeded'] else 'failed')
        except Exception as exc:
            logger.exception('刷新任务失败 %s', job['job_id'])
            with self._lock:
                job.update(status='failed', error=str(exc)[:500], retry_codes=job['codes'][:])
        finally:
            with self._lock:
                job.update(finished_at=now(), updated_at=now())
                job['message'] = f"已处理 {job['processed']}/{job['total']}，成功 {job['succeeded']}，失败 {job['failed']}，未处理 {job['remaining']}"
                try:
                    self._save(job)
                except OSError as exc:
                    job.update(status='failed', error=f'任务记录保存失败: {exc}', retry_codes=job['codes'][:])
                    logger.exception('无法保存刷新终态')

    def stop_admission(self):
        with self._lock:
            self._closing = True

    async def close(self, timeout=30):
        self.stop_admission()
        with self._lock:
            pending = [asyncio.wrap_future(f) for f in self._futures.values() if not f.done()]
        if pending:
            # Never cancel the underlying futures or release ownership while writing.
            await asyncio.wait(pending, timeout=timeout)
        self._executor.shutdown(wait=False, cancel_futures=False)
