from concurrent.futures import ThreadPoolExecutor
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api import routes
from src.services.favorites_service import FavoritesService


def test_batch_preserves_metadata_and_partial_failures(tmp_path):
    svc = FavoritesService(file_path=tmp_path / 'favorites.json')
    svc.add('000001', note='keep')
    svc.update_alerts('000001', {'enabled': True, 'levels': {}})
    before = svc.get_all()['items'][0]
    results, data = svc.add_batch(['000001', '000090', '000090', 'abc', '90'])
    assert [item['status'] for item in results] == ['already_exists', 'added', 'failed', 'failed']
    assert data['items'][0] == before
    assert 'alerts' not in data['items'][1]
    assert json.loads(svc.file_path.read_text()) == data


def test_batch_write_failure_rolls_back(tmp_path, monkeypatch):
    svc = FavoritesService(file_path=tmp_path / 'favorites.json')
    svc.add('000001')
    before = svc.get_all()
    def fail():
        raise OSError('disk full')
    monkeypatch.setattr(svc, '_save', fail)
    results, data = svc.add_batch(['000001', '000090'])
    assert [item['status'] for item in results] == ['already_exists', 'failed']
    assert data == before == svc.get_all()


def test_batch_concurrent_adds(tmp_path):
    svc = FavoritesService(file_path=tmp_path / 'favorites.json')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: svc.add_batch([f'{n:06}']), range(20)))
    assert len(svc.get_all()['codes']) == 20
    assert len(json.loads(svc.file_path.read_text())['codes']) == 20


def test_batch_static_route_and_validation(tmp_path, monkeypatch):
    svc = FavoritesService(file_path=tmp_path / 'favorites.json')
    monkeypatch.setattr(routes, 'favorites_service', svc)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    response = client.post('/favorites/batch', json={'codes': ['000090', 'abc']})
    assert response.status_code == 200
    assert response.json()['favorites']['codes'] == ['000090']
    assert response.json()['items'][1]['status'] == 'failed'
    assert client.post('/favorites/batch', json={'codes': []}).status_code == 422
