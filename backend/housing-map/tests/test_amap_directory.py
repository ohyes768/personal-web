import pytest

from src.services import amap_directory as amap
from src.services.residential_classifier import classify_sources


def poi(sid='1', name='风雅钱塘', **extra):
    return dict(id=sid, name=name, type='商务住宅;住宅区;住宅小区', typecode='120302',
                adname='滨江区', address='月明路1076号', location='120.207490,30.202261', **extra)


def test_filters_district_bounds_and_subordinate_pois():
    for field, value in [('adname', '萧山区'), ('location', '116.4,39.9'),
                         ('typecode', '120201'), ('name', '风雅钱塘北门'), ('name', '风雅钱塘12号楼')]:
        row = poi(); row[field] = value
        assert amap.normalize_poi(row) is None
    assert amap.normalize_poi(poi(name='测试花园西区'))['name'] == '测试花园西区'
    row = poi(); row['location'] = 'NaN,30.2'
    with pytest.raises(ValueError): amap.normalize_poi(row)


def test_map_hint_never_overrides_property_use():
    hint = amap.normalize_poi(poi())
    assert classify_sources([hint]) == 'pending'
    assert classify_sources([hint, {'source': 'tmsf', 'source_id': 't', 'property_type': '住宅'}]) == 'residential'
    assert classify_sources([hint, {'source': 'tmsf', 'source_id': 't', 'property_type': '写字楼'}]) == 'non_residential'
    assert classify_sources([hint, {'source': 'tmsf', 'source_id': 't', 'property_type': '公寓'}]) == 'pending'


def test_transport_error_cannot_leak_key(monkeypatch):
    monkeypatch.setenv('AMAP_WEB_SERVICE_KEY', 'private-key')
    client = amap.AmapClient()
    def failed(*args, **kwargs): raise RuntimeError('https://example?key=private-key')
    monkeypatch.setattr(client.session, 'get', failed)
    try:
        with pytest.raises(ValueError, match='高德位置补全请求失败') as exc:
            client.search_name('风雅钱塘', '滨江')
        assert 'private-key' not in str(exc.value)
    finally: client.close()
