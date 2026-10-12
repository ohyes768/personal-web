import asyncio
import threading

import httpx
import pandas as pd
from fastapi import FastAPI

from src.api import routes
from src.services.refresh_jobs import RefreshJobManager


def test_routes_accept_query_and_reuse_without_blocking(tmp_path, monkeypatch):
    async def scenario():
        manager = RefreshJobManager(tmp_path / 'jobs')
        monkeypatch.setattr(routes, 'refresh_jobs', manager, raising=False)
        gate = threading.Event()
        class M120:
            def update_m120_data(self, codes, show_progress=True, on_progress=None):
                gate.wait(2)
                on_progress(codes[0], True)
                return 1
        monkeypatch.setattr(routes, 'data_reader', object())
        monkeypatch.setattr(routes, 'm120_service', M120())
        app = FastAPI()
        app.include_router(routes.router, prefix='/api/dividend')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await asyncio.wait_for(client.post('/api/dividend/m120/refresh', json={'codes': ['000090']}), 0.5)
            assert response.status_code == 202
            job = response.json()
            duplicate = await client.post('/api/dividend/m120/refresh', json={'codes': ['600000']})
            assert duplicate.json()['reused'] is True
            assert duplicate.json()['job_id'] == job['job_id']
            latest = await client.get('/api/dividend/refresh/jobs?kind=m120')
            assert latest.json()['job_id'] == job['job_id']
            assert (await client.get('/api/dividend/refresh/jobs/missing')).status_code == 404
            assert (await client.get('/api/dividend/refresh/jobs?kind=bad')).status_code == 422
            assert (await client.post('/api/dividend/m120/refresh', json={'codes': ['invalid']})).status_code == 422
            gate.set()
            await manager.close(timeout=2)
            assert (await client.get(f"/api/dividend/refresh/jobs/{job['job_id']}")).json()['status'] == 'succeeded'
    asyncio.run(scenario())


def test_atomic_csv_failure_preserves_old_file(tmp_path, monkeypatch):
    from src.utils.atomic_file import atomic_csv
    path = tmp_path / 'data.csv'
    path.write_text('old', encoding='utf-8')
    def fail(*args, **kwargs):
        raise OSError('write failed')
    monkeypatch.setattr(pd.DataFrame, 'to_csv', fail)
    import pytest
    with pytest.raises(OSError):
        atomic_csv(pd.DataFrame({'股票代码': ['000090']}), path)
    assert path.read_text() == 'old'
    assert list(tmp_path.iterdir()) == [path]


def test_financial_force_batch_merge_and_throttle(tmp_path, monkeypatch):
    from src.data.financial_fetcher import FinancialFetcher
    async def scenario():
        manager = RefreshJobManager(tmp_path / 'jobs')
        monkeypatch.setattr(routes, 'refresh_jobs', manager)
        class Reader:
            def read_csv(self, strict=False):
                return pd.DataFrame({'股票代码': ['000090', '600000'], 'ROE': [1, 2]})
            def check_exists(self):
                return True
        monkeypatch.setattr(routes, 'data_reader', Reader())
        monkeypatch.setattr(routes, 'financial_reader', Reader())
        path = tmp_path / 'financial.csv'
        monkeypatch.setattr(routes, 'aux_file_path', lambda name: path)
        monkeypatch.setattr(routes, 'find_latest_aux_file', lambda name: path)
        monkeypatch.setattr(routes, 'days_since_update', lambda path: 1)
        monkeypatch.setattr(FinancialFetcher, 'fetch_one', lambda self, code: {'股票代码': code, 'ROE': 15} if code == '000090' else None)
        monkeypatch.setattr('src.data.financial_fetcher.time.sleep', lambda delay: None)
        app = FastAPI()
        app.include_router(routes.router)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            assert (await client.post('/financial/refresh', json={'codes': ['000090']})).status_code == 429
            response = await client.post('/financial/refresh?force=true', json={'codes': ['000090', '600000']})
            assert response.status_code == 202
            await manager.close(timeout=2)
            job = manager.get(response.json()['job_id'])
            assert job['status'] == 'partial_failed'
            assert (job['succeeded'], job['failed']) == (1, 1)
            saved = pd.read_csv(path, dtype={'股票代码': str})
            assert saved['股票代码'].tolist() == ['600000', '000090']
            assert saved.loc[saved['股票代码'] == '000090', 'ROE'].item() == 15
    asyncio.run(scenario())
