"""Public name discovery through the end of each source. Source failures are independent and visible."""
import json
import datetime as dt
import logging
import sqlite3
import threading
from types import SimpleNamespace

from src.services.community_registry import now, dump

logger = logging.getLogger(__name__)


class DiscoveryTruncated(Exception):
    pass


def check(cancel):
    if cancel.is_set():
        raise InterruptedError('采集已取消')


def pause(cancel):
    if cancel.wait(2):
        raise InterruptedError('采集已取消')


def tmsf_names(cancel, ignored, existing=None):
    from scripts.fetch_tmsf_binjiang_communities import fetch_binjiang_communities
    from src.services.tmsf_fetcher import TmsfClient
    from src.services.tmsf_property_type import fetch_community_facts, fetch_project_facts, parse_project_index, find_project, project_identity, PROJECT_INDEX_URL
    existing = existing or {}
    client = TmsfClient()
    projects = None
    project_index_error = False
    try:
        discovered = list(fetch_binjiang_communities())
        discovered_ids = {str(c.community_id) for c in discovered}
        # Previously imported identities may disappear from the current name list.
        for sid, previous in existing.items():
            if previous.get('address_verification_pending') and sid not in discovered_ids:
                discovered.append(SimpleNamespace(community_id=sid, community_name=previous['name'],
                    community_alias='', district=previous.get('district'), subdistrict=previous.get('subdistrict', ''),
                    source_url=previous.get('source_url')))
        for c in discovered:
            check(cancel)
            if c.district != '滨江':
                continue
            row = dict(source='tmsf', source_kind='community', source_id=c.community_id,
                       name=c.community_name, aliases=[c.community_alias] if c.community_alias else [],
                       district=c.district, subdistrict=c.subdistrict, source_url=c.source_url)
            previous = existing.get(str(c.community_id), {})
            for field in ('property_type', 'property_type_url', 'property_type_captured_at', 'address', 'address_origin', 'address_checked_at', 'address_verification_pending',
                          'market_state', 'market_state_url', 'market_state_captured_at',
                          'listing_count', 'listing_count_checked_at', 'listing_count_error',
                          'project_id', 'project_name', 'project_sale_status', 'project_aliases', 'property_type_conflict'):
                if field in previous:
                    row[field] = previous[field]
            # Publish the name before requesting details, including when cancelled later.
            yield {**row, '_stage': 'names'}
            if ignored('tmsf', 'community', c.community_id):
                continue
            if previous.get('market_state') == 'new_house' and previous.get('address_checked_at') and not previous.get('address_verification_pending') and previous.get('property_type') and not previous.get('property_type_error') and previous.get('name') == c.community_name:
                try:
                    age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(previous['property_type_captured_at'])
                    if dt.timedelta(0) <= age < dt.timedelta(days=30):
                        yield {**row, '_stage': 'property_type', '_property_type_result': 'cached'}
                        continue
                except (KeyError, ValueError, TypeError):
                    pass
            yield {**row, '_stage': 'property_type'}
            pause(cancel)
            if ignored('tmsf', 'community', c.community_id):
                continue
            row.update(_stage='property_type', property_type_checked_at=now())
            try:
                try:
                    detail = fetch_community_facts(client, c.community_id, [c.community_name, c.community_alias])
                except Exception:
                    check(cancel)
                    if projects is None and not project_index_error:
                        pause(cancel)
                        try:
                            projects = parse_project_index(client.fetch_text(PROJECT_INDEX_URL, 15))
                        except Exception:
                            project_index_error = True
                    if project_index_error:
                        raise ValueError('新房索引获取失败')
                    pause(cancel)
                    if ignored('tmsf', 'community', c.community_id):
                        continue
                    row.update(project_identity(find_project(projects, [c.community_name, c.community_alias], c.district)),
                               market_state_captured_at=now())
                    detail = fetch_project_facts(client, [c.community_name, c.community_alias], c.district, projects=projects)
                    detail['market_state_captured_at'] = now()
                # An ESF page also exists for many new projects; low listings are
                # not evidence that the project belongs only to the second-hand market.
                count = detail.get('listing_count')
                if detail.get('market_state') == 'second_hand' and (previous.get('market_state') == 'new_house' or
                        (isinstance(count, int) and not isinstance(count, bool) and count < 3)):
                    if projects is None and not project_index_error:
                        pause(cancel)
                        try:
                            projects = parse_project_index(client.fetch_text(PROJECT_INDEX_URL, 15))
                        except Exception:
                            project_index_error = True
                    check(cancel)
                    if ignored('tmsf', 'community', c.community_id):
                        continue
                    try:
                        detail.update(project_identity(find_project(projects or [], [c.community_name, c.community_alias], c.district)),
                                      market_state_captured_at=now(), market_state_error=None)
                    except ValueError:
                        if previous.get('market_state') == 'new_house':
                            detail.pop('market_state', None)
                            detail['market_state_error'] = '新房项目身份更新失败，保留已有证据'
                row.update(detail)
                if detail.get('market_state') == 'second_hand':
                    row['listing_count_checked_at'] = now()
                row.update(address_checked_at=now(), address_origin='source_detail', address_verification_pending=False,
                           property_type_captured_at=now(), property_type_error=None,
                           _property_type_result='succeeded')
            except InterruptedError:
                raise
            except Exception as exc:
                message = f'{c.community_name} 物业类型获取失败（{type(exc).__name__}）'
                row.update(listing_count_error=message, listing_count_checked_at=now(), property_type_error=message, _property_type_result='failed',
                           _collection_errors=[dict(source='tmsf', stage='property_type',
                                                    source_id=c.community_id, message=message)])
            yield row
    finally:
        client.close()


def fang_names(cancel, ignored):
    from src.services.fang_rentals import FangClient, parse_listing_page, enrich_detail
    client = FangClient(timeout=20)
    url = 'https://zu.fang.com/hz/house-a0154/n31/'
    visited = set()
    try:
        while True:
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
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        row['quality_flags'].append('detail_fetch_failed')
                        row['_collection_error'] = dict(source='fang', stage='detail',
                            source_id=sid, listing_id=row['source_listing_id'],
                            message=f"房源 {row['source_listing_id']} 详情采集失败（{type(exc).__name__}）")
                grouped.setdefault(sid, []).append(row)
            for sid, samples in grouped.items():
                yield dict(source='fang', source_kind='community', source_id=sid,
                           name=samples[0]['community_name'], district='滨江',
                           address=next((s.get('address') for s in samples if s.get('address')), ''),
                           source_url=f'https://zu.fang.com/hz/house-xm{sid}/', samples=samples,
                           _collection_errors=[s.pop('_collection_error') for s in samples if '_collection_error' in s])
            if not next_url:
                return
            if next_url in visited:
                raise DiscoveryTruncated('房天下分页重复，名称覆盖不完整')
            url = next_url
            pause(cancel)
    finally:
        client.close()


def laipai_names(cancel, ignored):
    from src.services.auction_fetcher import AuctionClient, normalize_auction
    client = AuctionClient()
    scanned = 0
    page = 1
    visited = set()
    try:
        while True:
            check(cancel)
            data = client.list_page(page)
            identities = tuple(sorted(str(item.get('auction_id')) for item in data['list']))
            if identities and identities in visited:
                raise DiscoveryTruncated('来拍分页重复，滨江名称覆盖不完整')
            visited.add(identities)
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
            if not data['list']:
                if scanned < data['count']:
                    raise DiscoveryTruncated('来拍列表提前结束，滨江名称覆盖不完整')
                return
            if scanned >= data['count']:
                return
            page += 1
            pause(cancel)
    finally:
        client.close()


ADAPTERS = {'tmsf': tmsf_names, 'fang': fang_names, 'laipai': laipai_names}


def _check_sources(sources):
    if 'amap' in sources:
        raise ValueError('高德小区名单采集已停止，请使用透明售房网')


def collect_names(store, sources, *, cancel=None, adapters=None, progress=None):
    _check_sources(sources)
    cancel = cancel or threading.Event()
    adapters = adapters or ADAPTERS
    report = dict(phase='running', running=True, started_at=now(), source=None,
                  stage='names', property_types=0, property_types_failed=0, property_types_cached=0,
                  new=0, existing=0, ignored=0, matched=0, pending=0, errors=[], truncated=[])
    handled = set()
    counted_status = {}
    failed_sources = set()
    try:
        initial = store.sources()
        seen = {(r['source'], r['source_kind'], r['source_id']) for r in initial}
        for source in sources:
            check(cancel)
            report['source'] = source
            report['stage'] = 'names'
            if progress:
                progress(report)
            try:
                adapter = adapters[source]
                kwargs = {}
                if adapter is tmsf_names:
                    from src.services.residential_classifier import _load_property_types
                    legacy = _load_property_types(store.path.parent / 'property_types.json')
                    existing = {}
                    for record in initial:
                        if record['source'] != 'tmsf':
                            continue
                        previous = dict(record)
                        if not record.get('property_type') and not record.get('property_type_checked_at'):
                            old = legacy.get(record['source_id'], {})
                            previous.update(property_type=old.get('property_type'), property_type_url=old.get('url'),
                                            property_type_captured_at=old.get('captured_at'))
                        existing[record['source_id']] = previous
                    kwargs['existing'] = existing
                for row in adapter(cancel, store.is_ignored, **kwargs):
                    check(cancel)
                    report['stage'] = row.pop('_stage', 'names')
                    type_result = row.pop('_property_type_result', None)
                    key = (source, row.get('source_kind', 'community'), str(row['source_id']))
                    if store.is_ignored(*key):
                        if key not in handled:
                            report['ignored'] += 1
                    else:
                        if type_result:
                            counter = {'succeeded': 'property_types', 'failed': 'property_types_failed', 'cached': 'property_types_cached'}[type_result]
                            report[counter] += 1
                        report['errors'].extend(row.pop('_collection_errors', []))
                        item = store.ingest(row)
                        status = 'matched' if item['status'] == 'matched' else 'pending'
                        if key not in handled:
                            report['existing' if key in seen else 'new'] += 1
                            report[status] += 1
                        elif key in counted_status and counted_status[key] != status:
                            report[counted_status[key]] -= 1
                            report[status] += 1
                        counted_status[key] = status
                    handled.add(key)
                    if progress:
                        progress(report)
            except DiscoveryTruncated as exc:
                report['truncated'].append({'source': source, 'message': str(exc)})
            except InterruptedError:
                raise
            except Exception as exc:
                failed_sources.add(source)
                # Upstream clients redact request URLs and credentials before reporting errors.
                report['errors'].append({'source': source, 'message': str(exc) if isinstance(exc, ValueError) else f'{type(exc).__name__}：来源请求失败'})
        report['phase'] = 'partial_failed' if report['errors'] or report['truncated'] else 'succeeded'
        if len(failed_sources) == len(sources):
            report['phase'] = 'failed'
    except InterruptedError:
        report['phase'] = 'cancelled'
    except Exception as exc:
        logger.exception('Community name collection failed')
        report['phase'] = 'failed'
        report['errors'].append(dict(source='directory', stage='task',
                                    message=f'{type(exc).__name__}：采集任务失败'))
    finally:
        if report.get('new') or report.get('existing'):
            try:
                from src.services.community_review import ReviewWorkspace
                ReviewWorkspace(store, store.path.parent).refresh()
            except Exception:
                report['errors'].append(dict(source='directory', stage='review', message='资料已保存，审核队列同步未完成，请刷新或重试同步'))
                if report['phase'] == 'succeeded':
                    report['phase'] = 'partial_failed'
            else:
                try:
                    from src.services.community_auto_review import AutoReview
                    report['auto_review'] = AutoReview(store, store.path.parent).after_collection()
                except Exception:
                    report['errors'].append(dict(source='directory', stage='auto_review', message='资料和审核队列已保存，自动审核未完成，请重新预演'))
                    if report['phase'] == 'succeeded':
                        report['phase'] = 'partial_failed'
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
        self.state = json.loads(dump(state))
        try:
            with self.store.db() as db:
                db.execute("INSERT INTO meta VALUES ('collection_job',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dump(state),))
        except (sqlite3.Error, OSError):
            self.state.update(running=False, phase='failed', finished_at=now())
            self.state.setdefault('errors', []).append(dict(source='directory', stage='save', message='采集报告保存失败'))
            logger.exception('Could not persist community collection report')
            if state.get('running'):
                raise

    def start(self, sources):
        _check_sources(sources)
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError('名称采集正在运行')
            self.cancel.clear()
            self._save({'running': True, 'phase': 'running', 'started_at': now()})
            self.worker = threading.Thread(target=collect_names, args=(self.store, sources),
                kwargs={'cancel': self.cancel, 'progress': self._save}, daemon=True)
            self.worker.start()
        return self.state

    def shutdown(self):
        self.cancel.set()
        if self.worker:
            self.worker.join()
