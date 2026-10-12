import asyncio
import pandas as pd
import pytest

from src.api import routes
from src.services.m120_service import M120Service
from src.services.refresh_jobs import RefreshJobManager


def test_m120_limit_reports_failed_and_unprocessed_and_can_retry(tmp_path, monkeypatch):
    monkeypatch.setattr('src.services.m120_service.DATA_DIR', tmp_path)
    monkeypatch.setattr('src.services.m120_service.time.sleep', lambda _: None)
    service = M120Service()
    progress = []
    monkeypatch.setattr(service, '_get_m120_from_aliyun', lambda code: None)
    codes = [f'60000{i}' for i in range(7)]
    assert service.update_m120_data(codes, on_progress=lambda c, ok: progress.append((c, ok))) == 0
    assert progress == [(c, False) for c in codes[:5]]
    monkeypatch.setattr(service, '_get_m120_from_aliyun', lambda code: {'m120': 15})
    assert service.update_m120_data(['000090']) == 1
    assert service.read_m120_data()['000090']['m120'] == 15


def test_m120_save_failure_keeps_old_file(tmp_path, monkeypatch):
    monkeypatch.setattr('src.services.m120_service.DATA_DIR', tmp_path)
    service = M120Service()
    path = service.M120_CSV_FILE
    path.write_text('日期,股票代码,M120\n2026-10,000090,12\n', encoding='utf-8-sig')
    old = path.read_bytes()
    monkeypatch.setattr(service, '_get_m120_from_aliyun', lambda code: {'m120': 15})
    def fail(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr('src.utils.atomic_file.os.replace', fail)
    with pytest.raises(OSError):
        service.update_m120_data(['000090'])
    assert path.read_bytes() == old


def test_financial_publish_failure_is_failed_and_preserves_old(tmp_path, monkeypatch):
    async def scenario():
        path = tmp_path / 'financial.csv'
        path.write_text('股票代码,ROE\n000090,12\n', encoding='utf-8-sig')
        old = path.read_bytes()
        class Reader:
            def check_exists(self): return True
            def read_csv(self, strict=False): return pd.read_csv(path, dtype={'股票代码': str})
        monkeypatch.setattr(routes, 'financial_reader', Reader())
        monkeypatch.setattr(routes, 'aux_file_path', lambda name: path)
        monkeypatch.setattr('src.data.financial_fetcher.FinancialFetcher.fetch_one', lambda self, code: {'股票代码': code, 'ROE': 15})
        def fail(*args): raise OSError('disk full')
        monkeypatch.setattr(routes, 'atomic_csv', fail)
        manager = RefreshJobManager(tmp_path / 'jobs')
        job = manager.submit('financial', ['000090'], lambda p: routes._run_financial_refresh(['000090'], True, p))
        await manager.close(timeout=2)
        result = manager.get(job['job_id'])
        assert result['status'] == 'failed'
        assert result['retry_codes'] == ['000090']
        assert path.read_bytes() == old
    asyncio.run(scenario())


def test_financial_corrupt_cache_is_not_overwritten(tmp_path, monkeypatch):
    from src.services.shareholder_financial_reader import FinancialReader
    path = tmp_path / 'financial.csv'
    path.write_text('broken\ncache\n', encoding='utf-8-sig')
    old = path.read_bytes()
    reader = FinancialReader()
    monkeypatch.setattr(reader, '_get_file_path', lambda: path)
    monkeypatch.setattr(routes, 'financial_reader', reader)
    monkeypatch.setattr(routes, 'aux_file_path', lambda name: path)
    monkeypatch.setattr('src.data.financial_fetcher.FinancialFetcher.fetch_one', lambda self, code: {'股票代码': code, 'ROE': 15})
    with pytest.raises(KeyError):
        routes._run_financial_refresh(['000090'], True, lambda *args: None)
    assert path.read_bytes() == old


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 0])
def test_m120_invalid_numeric_result_counts_as_failed(tmp_path, monkeypatch, value):
    monkeypatch.setattr('src.services.m120_service.DATA_DIR', tmp_path)
    service = M120Service()
    monkeypatch.setattr(service, '_get_m120_from_aliyun', lambda code: {'m120': value})
    progress = []
    assert service.update_m120_data(['000090'], on_progress=lambda c, ok: progress.append(ok)) == 0
    assert progress == [False]
