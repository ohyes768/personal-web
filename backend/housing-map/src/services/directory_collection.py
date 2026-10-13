"""Bounded public name discovery. Source failures are independent and visible."""
import json
import os
import threading
from urllib.parse import quote

from src.services.community_registry import now, dump


class DiscoveryTruncated(Exception):
    pass


def check(cancel):
    if cancel.is_set():
        raise InterruptedError('采集已取消')


def pause(cancel):
    if cancel.wait(2):
        raise InterruptedError('采集已取消')


def tmsf_names(cancel, limit, ignored):
    from scripts.fetch_tmsf_binjiang_communities import fetch_binjiang_communities
    for c in fetch_binjiang_communities():
        check(cancel)
        if c.district == '滨江':
            yield dict(source='tmsf', source_kind='community', source_id=c.community_id,
                       name=c.community_name, aliases=[c.community_alias] if c.community_alias else [],
                       district=c.district, subdistrict=c.subdistrict, source_url=c.source_url)


def fang_names(cancel, limit, ignored):
    from src.services.fang_rentals import FangClient, parse_listing_page, enrich_detail
    client = FangClient(timeout=20)
    url = 'https://zu.fang.com/hz/house-a0154/n31/'
    visited = set()
    try:
        for _ in range(limit):
            check(cancel)
            visited.add(url)
            rows, next_url = parse_listing_page(client.fetch(url), url)
            grouped = {}
            for row in rows:
                sid = row.get('source_community_id')
                if not sid or not row.get('community_name'):
                    continue
                row['captured_at'] = now()
                if not ignored('fang', 'community', sid):
                    pause(cancel)
                    try:
                        enrich_detail(row, client.fetch(row['source_url']))
                    except Exception:
                        row['quality_flags'].append('detail_fetch_failed')
                grouped.setdefault(sid, []).append(row)
            for sid, samples in grouped.items():
                yield dict(source='fang', source_kind='community', source_id=sid,
                           name=samples[0]['community_name'], district='滨江',
                           address=next((s.get('address') for s in samples if s.get('address')), ''),
                           source_url=f'https://zu.fang.com/hz/house-xm{sid}/', samples=samples)
            if not next_url or next_url in visited:
                return
            url = next_url
            pause(cancel)
        raise DiscoveryTruncated('房天下分页达到上限，名称与样本覆盖不完整')
    finally:
        client.close()


def amap_names(cancel, limit, ignored):
    from curl_cffi.requests import Session
    key = os.getenv('AMAP_WEB_SERVICE_KEY') or os.getenv('GAODE_API_KEY')
    if not key:
        try:
            from scripts._gaode_config import GAODE_API_KEY
            key = GAODE_API_KEY
        except ImportError:
            pass
    if not key:
        raise ValueError('未配置高德 Web 服务 Key（AMAP_WEB_SERVICE_KEY 或 GAODE_API_KEY）')
    scanned = 0
    with Session() as session:
        for page in range(1, min(limit, 8) + 1):
            check(cancel)
            response = session.get('https://restapi.amap.com/v3/place/text', params={
                'key': key, 'city': '330108', 'citylimit': 'true', 'types': '120302',
                'offset': 25, 'page': page, 'extensions': 'base'}, timeout=20)
            response.raise_for_status()
            data = response.json()
            if data.get('status') != '1' or not isinstance(data.get('pois'), list):
                raise ValueError('高德名称采集不可用，请检查 Key 和配额')
            pois = data['pois']
            for p in pois:
                if p.get('adname') != '滨江区' or any(t in p.get('name', '') for t in ('出入口', '停车场', '幢', '栋')):
                    continue
                lng, lat = map(float, p['location'].split(','))
                yield dict(source='amap', source_kind='poi', source_id=p['id'], name=p['name'],
                           district='滨江', address=p.get('address') if isinstance(p.get('address'), str) else '',
                           longitude=lng, latitude=lat, coordinate_system='gcj02',
                           source_url='https://www.amap.com/search?query=' + quote(p['name']))
            scanned += len(pois)
            if not pois and scanned < int(data.get('count', 0)):
                raise DiscoveryTruncated('高德搜索结果受上游数量限制，目录覆盖不完整')
            if not pois or scanned >= int(data.get('count', 0)):
                return
            pause(cancel)
    raise DiscoveryTruncated('高德分页达到上限，目录覆盖不完整')


def laipai_names(cancel, limit, ignored):
    from src.services.auction_fetcher import AuctionClient, normalize_auction
    client = AuctionClient()
    scanned = 0
    try:
        for page in range(1, limit + 1):
            check(cancel)
            data = client.list_page(page)
            for item in data['list']:
                if str(item.get('area_code')) != '330108':
                    continue
                aid = str(item.get('auction_id'))
                asset = str(item.get('object_id') or '')
                if ignored('laipai', 'auction', aid) or (asset and ignored('laipai', 'asset', asset)):
                    yield dict(source='laipai', source_kind='asset' if asset else 'auction',
                               source_id=asset or aid, name=item.get('cell_name') or '已删除标的', district='滨江')
                    continue
                pause(cancel)
                row = normalize_auction(client.detail(aid), [])
                if row and row.get('community_name'):
                    yield dict(source='laipai', source_kind='asset', source_id=row['asset_id'],
                               auction_ids=[row['auction_id']],
                               name=row['community_name'], district='滨江', address=row['address'],
                               source_url=row['source_url'])
            scanned += len(data['list'])
            if not data['list'] or scanned >= data['count']:
                return
            pause(cancel)
        raise DiscoveryTruncated('来拍杭州列表达到分页上限，滨江名称覆盖不完整')
    finally:
        client.close()


ADAPTERS = {'tmsf': tmsf_names, 'fang': fang_names, 'amap': amap_names, 'laipai': laipai_names}


def collect_names(store, sources, *, max_pages=10, cancel=None, adapters=None, progress=None):
    cancel = cancel or threading.Event()
    adapters = adapters or ADAPTERS
    report = dict(phase='running', running=True, started_at=now(), source=None,
                  new=0, existing=0, ignored=0, matched=0, pending=0, errors=[], truncated=[])
    seen = {(r['source'], r['source_kind'], r['source_id']) for r in store.sources()}
    handled = set()
    try:
        for source in sources:
            check(cancel)
            report['source'] = source
            if progress:
                progress(report)
            try:
                for row in adapters[source](cancel, max_pages, store.is_ignored):
                    check(cancel)
                    key = (source, row.get('source_kind', 'community'), str(row['source_id']))
                    if store.is_ignored(*key):
                        if key not in handled:
                            report['ignored'] += 1
                    else:
                        item = store.ingest(row)
                        if key not in handled:
                            report['existing' if key in seen else 'new'] += 1
                            report['matched' if item['status'] == 'matched' else 'pending'] += 1
                    handled.add(key)
                    if progress:
                        progress(report)
            except DiscoveryTruncated as exc:
                report['truncated'].append({'source': source, 'message': str(exc)})
            except InterruptedError:
                raise
            except Exception as exc:
                # Never include request URLs (Amap keys) in reports.
                report['errors'].append({'source': source, 'message': str(exc) if isinstance(exc, ValueError) else f'{type(exc).__name__}：来源请求失败'})
        report['phase'] = 'partial_failed' if report['errors'] or report['truncated'] else 'succeeded'
        if len(report['errors']) == len(sources):
            report['phase'] = 'failed'
    except InterruptedError:
        report['phase'] = 'cancelled'
    finally:
        report.update(running=False, source=None, finished_at=now())
        if progress:
            progress(report)
    return report


class DirectoryJob:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.worker = None
        self.state = self._read()
        if self.state and self.state.get('running'):
            self.state.update(running=False, phase='interrupted')
            self._save(self.state)

    def _read(self):
        with self.store.db() as db:
            r = db.execute("SELECT value FROM meta WHERE key='collection_job'").fetchone()
            return json.loads(r[0]) if r else None

    def _save(self, state):
        self.state = dict(state)
        with self.store.db() as db:
            db.execute("INSERT INTO meta VALUES ('collection_job',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dump(state),))

    def start(self, sources, max_pages):
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError('名称采集正在运行')
            self.cancel.clear()
            self._save({'running': True, 'phase': 'running', 'started_at': now()})
            self.worker = threading.Thread(target=collect_names, args=(self.store, sources),
                kwargs={'max_pages': max_pages, 'cancel': self.cancel, 'progress': self._save}, daemon=True)
            self.worker.start()
        return self.state

    def shutdown(self):
        self.cancel.set()
        if self.worker:
            self.worker.join()
