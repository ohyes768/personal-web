"""租金“继续采集”：待采集数量与继续采集共用同一套筛选条件。

数量统计和实际下手的对象必须来自同一份名单（已收录住宅 × 已关联来源），
否则按钮上的数字会骗人。完成判定 = 当前来源 + 已发布的完整快照 + 最近一次采集成功。
"""
import datetime as dt

from src.services.fang_rentals import SeedRunResult
from src.services.rental_reference.refresh import RentalRefreshService
from src.services.rental_reference.storage import CommunityBatch, load_current, publish_run
from src.services.xingfuli_rentals import list_url
from tests.test_rental_providers import registry, source


def forbidden(**kwargs):
    raise AssertionError('source discovery / Fang must not run during rent collection')


def client(calls, status='empty_ok'):
    """幸福里列表接口替身：记录被采的小区来源号。"""

    class Client:
        request_count = 1
        cooldown_until = None

        def __init__(self, **kwargs):
            pass

        def crawl(self, sid, seed, **kwargs):
            calls.append(sid)
            return SeedRunResult(seed=list_url(seed), status=status, pages_fetched=1)

        def close(self):
            pass

    return Client


def service(tmp_path, reg, calls, status='empty_ok'):
    return RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                xingfuli_only=True, fetch_factory=forbidden,
                                discovery_factory=forbidden, xingfuli_factory=client(calls, status))


def add_community(reg, community_id, sid, seed):
    """再挂一个已收录住宅及其幸福里来源。"""
    reg.create('第二花园', community_id=community_id, district='滨江', address='测试路2号')
    fact = reg.ingest(dict(source='tmsf', source_id=community_id, name='第二花园', district='滨江',
                           address='测试路2号', property_type='住宅', listing_count=3,
                           market_state='second_hand'))
    reg.associate(fact['id'], community_id)
    record = reg.ingest(dict(source='xingfuli', source_id=sid, name='第二花园', district='滨江',
                             address='测试路2号', seed_listing_id=seed,
                             auto_association_disabled=True, source_url=list_url(seed)))
    reg.associate(record['id'], community_id)
    return record


def test_continuation_count_is_zero_after_a_published_snapshot(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'xingfuli')
    calls = []
    svc = service(tmp_path, reg, calls)
    assert svc.continuation_count() == 1
    svc.start()
    svc._thread.join(5)
    assert svc.status()['phase'] == 'done', svc.status()
    # 已查完并发布成功的小区不再重复采集。
    assert svc.continuation_count() == 0


def test_continue_mode_crawls_only_what_is_missing(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'xingfuli')
    calls = []
    svc = service(tmp_path, reg, calls)
    svc.start()
    svc._thread.join(5)
    assert calls == ['123']

    add_community(reg, 'c2', 'sid2', '7502229388495274019')
    assert svc.continuation_count() == 1

    calls.clear()
    svc.start(mode='continue')
    svc._thread.join(5)
    # 只补新来的那个小区，完成的小区不重爬。
    assert calls == ['sid2']
    # 已完成小区的数据保留，新小区的数据补进快照。
    assert set(load_current(tmp_path / 'rentals')['communities']) == {'pilot', 'c2'}


def test_failed_crawl_keeps_old_snapshot_but_stays_pending(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'xingfuli')
    old = dt.datetime.now(dt.UTC) - dt.timedelta(days=2)
    publish_run(tmp_path / 'rentals', [CommunityBatch('pilot', 'xingfuli', '123', 'complete',
                                                       old.isoformat(), samples=[])])
    calls = []
    svc = service(tmp_path, reg, calls, status='list_failed')
    svc.start()
    svc._thread.join(5)
    assert svc.status()['phase'] == 'failed', svc.status()
    # 采集失败：旧快照留着，但这个小区仍算待采集。
    assert load_current(tmp_path / 'rentals')['communities']['pilot']['captured_at'] == old.isoformat()
    assert svc.continuation_count() == 1


def test_changed_source_is_collected_again(tmp_path):
    reg = registry(tmp_path)
    old_source = source(reg, 'xingfuli')
    calls = []
    svc = service(tmp_path, reg, calls)
    svc.start()
    svc._thread.join(5)
    assert svc.continuation_count() == 0

    reg.unlink(old_source['id'])
    source(reg, 'xingfuli', sid='456')
    # 换过来源的小区重新采集，旧快照不能算数。
    assert svc.continuation_count() == 1


def test_count_and_continue_use_the_same_scope(tmp_path):
    """数量算的是哪些，continue 就只采哪些。"""
    reg = registry(tmp_path)
    source(reg, 'xingfuli')
    calls = []
    svc = service(tmp_path, reg, calls)
    svc.start()
    svc._thread.join(5)
    add_community(reg, 'c2', 'sid2', '7502229388495274019')
    add_community(reg, 'c3', 'sid3', '7502229388495274020')
    assert svc.continuation_count() == 2

    calls.clear()
    svc.start(mode='continue')
    svc._thread.join(5)
    assert sorted(calls) == ['sid2', 'sid3']
    assert svc.continuation_count() == 0
