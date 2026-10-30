"""Public name discovery through the end of each source. Source failures are independent and visible."""
import json
import datetime as dt
import logging
import sqlite3
import threading
from types import SimpleNamespace

from src.services.community_registry import now, dump
from src.services.source_collection_state import collection_resolution

logger = logging.getLogger(__name__)


class DiscoveryTruncated(Exception):
    pass


def check(cancel):
    if cancel.is_set():
        raise InterruptedError('采集已取消')


def pause(cancel):
    if cancel.wait(2):
        raise InterruptedError('采集已取消')


def retryable_sources(records):
    """Stored failures, counted once per active source identity (not per error)."""
    return [r for r in records if r['source'] == 'tmsf' and r.get('status') != 'ignored'
            and r.get('source_kind', 'community') in {'community', 'project'}
            and (r.get('district') or '').removesuffix('区') == '滨江'
            and collection_resolution(r)['retryable']]


def continuable_sources(records):
    """Known unfinished details plus retryable failures; never human/source gaps."""
    return [r for r in records if r['source'] == 'tmsf' and r.get('status') != 'ignored'
            and r.get('source_kind', 'community') in {'community', 'project'}
            and (r.get('district') or '').removesuffix('区') == '滨江'
            and (collection_resolution(r)['retryable'] or
                 (collection_resolution(r)['state'] == 'facts_pending'
                  and not r.get('property_type_checked_at')
                  and not r.get('collection_error_code')
                  and not r.get('property_type_captured_at')))]


def tmsf_names(cancel, ignored, existing=None, *, retry_failed=False, resume=False):
    from scripts.fetch_tmsf_binjiang_communities import fetch_binjiang_communities
    from src.services.tmsf_fetcher import TmsfClient
    from src.services.community_registry import normalized
    from src.services.tmsf_property_type import fetch_community_facts, fetch_project_facts, fetch_project_facts_by_id, parse_project_index, find_project, project_identity, effective_market_state, PROJECT_INDEX_URL
    existing = existing or {}
    client = TmsfClient()
    client.cancelled = cancel.is_set
    projects = None
    project_index_error = False
    try:
        targets = (continuable_sources(existing.values()) if resume else retryable_sources(existing.values())) if retry_failed else []
        discovered = [SimpleNamespace(community_id=r['source_id'], community_name=r['name'],
                         community_alias='', district='滨江', subdistrict=r.get('subdistrict', ''),
                         source_url=r.get('source_url')) for r in targets if r['source_kind'] == 'community'] \
            if retry_failed else list(fetch_binjiang_communities())
        discovered_ids = {str(c.community_id) for c in discovered}
        # Previously imported identities may disappear from the current name list.
        for (kind, sid), previous in existing.items():
            if not retry_failed and kind == 'community' and previous.get('address_verification_pending') and sid not in discovered_ids:
                discovered.append(SimpleNamespace(community_id=sid, community_name=previous['name'],
                    community_alias='', district=previous.get('district'), subdistrict=previous.get('subdistrict', ''),
                    source_url=previous.get('source_url')))
        for c in discovered:
            check(cancel)
            if c.district != '滨江':
                continue
            previous = existing.get(('community', str(c.community_id)), {})
            row = dict(source='tmsf', source_kind='community', source_id=c.community_id,
                       name=c.community_name, aliases=previous.get('aliases', []) if retry_failed else ([c.community_alias] if c.community_alias else []),
                       district=c.district, subdistrict=c.subdistrict, source_url=c.source_url)
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
            if not retry_failed and effective_market_state(previous) == 'new_house' and previous.get('address_checked_at') and not previous.get('address_verification_pending') and previous.get('property_type') and not previous.get('property_type_error') and previous.get('name') == c.community_name:
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
                    detail = fetch_community_facts(client, c.community_id, [c.community_name, *row['aliases']])
                    detail['market_state_error'] = None
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
                    row.update(project_identity(find_project(projects, [c.community_name, *row['aliases']], c.district)),
                               market_state_captured_at=now())
                    detail = fetch_project_facts(client, [c.community_name, *row['aliases']], c.district,
                                                 projects=projects, previous=previous, supplement_address=False)
                    detail['market_state_captured_at'] = now()
                    detail['market_state_error'] = None
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
                        if project_index_error:
                            raise ValueError('新房索引获取失败')
                        identity = project_identity(find_project(projects or [], [c.community_name, *row['aliases']], c.district))
                        if identity['market_state'] == 'unknown':
                            identity.pop('market_state')
                        detail.update(identity, market_state_captured_at=now(), market_state_error=None)
                    except ValueError:
                        if effective_market_state(previous) == 'new_house':
                            detail.pop('market_state', None)
                            detail['market_state_error'] = '新房项目身份更新失败，保留已有证据'
                        elif project_index_error:
                            detail['market_state_error'] = '新房索引获取失败，项目身份待重试'
                address_error = detail.get('address_error')
                address_pending = detail.get('address_pending', False)
                if address_error or address_pending:
                    detail.pop('address', None)
                row.update(detail)
                if detail.get('market_state') == 'second_hand':
                    row['listing_count_checked_at'] = now()
                if not address_error and not address_pending:
                    row.update(address_checked_at=now(), address_origin='source_detail', address_verification_pending=False, address_error=None)
                elif address_error:
                    row['address_error'] = address_error
                    row['_collection_errors'] = [dict(source='tmsf', stage='newhouse_address',
                        source_id=c.community_id, message=f'{c.community_name} {address_error}')]
                row.update(property_type_captured_at=now(), property_type_error=None, collection_error_code=None,
                           _property_type_result='succeeded')
                if detail.get('market_state') == 'new_house':
                    row['listing_count_error'] = None
                if detail.get('market_state_error'):
                    row.setdefault('_collection_errors', []).append(dict(source='tmsf', stage='market_state',
                        source_id=c.community_id, message=f'{c.community_name} {detail["market_state_error"]}'))
            except InterruptedError:
                raise
            except Exception as exc:
                message = f'{c.community_name} 物业类型获取失败（{getattr(exc, "code", type(exc).__name__)}）：{exc}'
                row.update(listing_count_error=message, listing_count_checked_at=now(), property_type_error=message,
                           collection_error_code=getattr(exc, 'code', type(exc).__name__), _property_type_result='failed',
                           _collection_errors=[dict(source='tmsf', stage='property_type',
                                                    source_id=c.community_id, message=message)])
            yield row
        # Independent discovery: sellable newhouse projects absent from the ESF name list.
        # Candidates publish before their details; a failed detail never drops the name.
        check(cancel)
        if retry_failed:
            projects = [dict(propertyid=r['source_id'], siteid=r.get('project_siteid', ''),
                            propertyname=r['name'], districtname='滨江', propertystateid=2)
                        for r in targets if r['source_kind'] == 'project']
            project_index_error = False
        if projects is None and not project_index_error:
            pause(cancel)
            try:
                projects = parse_project_index(client.fetch_text(PROJECT_INDEX_URL, 15))
            except Exception:
                project_index_error = True
        if project_index_error:
            yield dict(source='tmsf', source_kind='project', _errors_only=True, _stage='newhouse_index',
                       _collection_errors=[dict(source='tmsf', stage='newhouse_index', source_id='index',
                                                message='新房项目索引获取失败，本轮未发现新房候选')])
            return
        esf_names = {normalized(n) for c in discovered for n in [c.community_name, c.community_alias] if n}
        esf_names |= {normalized(n) for (kind, _), prev in existing.items() if kind == 'community'
                      for n in [prev.get('name'), *prev.get('aliases', [])] if n}
        for project in projects:
            check(cancel)
            if normalized(project.get('districtname')).removesuffix('区') != '滨江':
                continue
            status = {2: '在售', 3: '尾盘', 4: '售完', 5: '待售'}.get(project.get('propertystateid'), '未知')
            if status not in {'在售', '尾盘', '待售'}:
                continue  # 首期只发现未售完项目；售完项目由既有条目继续跟踪状态。
            try:
                identity = project_identity(project)
            except (KeyError, TypeError, ValueError):
                continue
            pid = str(project['propertyid'])
            names = identity['project_aliases']
            if not retry_failed and {normalized(n) for n in names if n} & esf_names:
                continue  # 名录已覆盖的项目走既有补充匹配，不产生重复候选。
            if ignored('tmsf', 'project', pid):
                continue
            row = dict(source='tmsf', source_kind='project', source_id=pid, name=identity['project_name'],
                       aliases=names, district='滨江', source_url=identity['project_url'],
                       market_state=identity['market_state'], market_state_url=identity['market_state_url'],
                       market_state_captured_at=now(), project_sale_status=status, project_id=pid,
                       project_siteid=str(project['siteid']), project_name=identity['project_name'],
                       project_aliases=names)
            previous = existing.get(('project', pid), {})
            if retry_failed:
                metadata = {'id', 'community_id', 'status', 'method', 'evidence'}
                row = {**{k: v for k, v in previous.items() if k not in metadata},
                       **{k: v for k, v in row.items() if k not in previous}}
            for field in ('property_type', 'property_type_url', 'property_type_captured_at',
                          'property_type_checked_at', 'address', 'address_origin', 'address_checked_at',
                          'address_error', 'property_type_error'):
                if field in previous:
                    row[field] = previous[field]
            yield {**row, '_stage': 'names'}
            if not retry_failed and previous.get('property_type') and previous.get('address') and previous.get('address_checked_at') \
                    and not previous.get('property_type_error') and not previous.get('address_error'):
                try:
                    age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(previous['property_type_captured_at'])
                    if dt.timedelta(0) <= age < dt.timedelta(days=30):
                        yield {**row, '_stage': 'property_type', '_property_type_result': 'cached'}
                        continue
                except (KeyError, ValueError, TypeError):
                    pass
            yield {**row, '_stage': 'property_type'}
            pause(cancel)
            if ignored('tmsf', 'project', pid):
                continue
            row.update(_stage='property_type', property_type_checked_at=now())
            try:
                detail = fetch_project_facts_by_id(client, siteid=project['siteid'], propertyid=project['propertyid'],
                                                   names=[identity['project_name'], *names], district='滨江', previous=previous,
                                                   supplement_address=False)
            except InterruptedError:
                raise
            except Exception as exc:
                code = getattr(exc, 'code', None)
                message = f'{identity["project_name"]} 新房详情获取失败（{code or type(exc).__name__}）：{exc}'
                deferred = code in {'paused', 'busy'}
                row['_newhouse_pause_reason'] = (getattr(exc, 'pause_reason', code)
                                                 if getattr(exc, 'task_paused', True) else None)
                row.update(property_type_error=message, _property_type_result='deferred' if deferred else 'failed',
                           collection_error_code=code or type(exc).__name__,
                           _collection_errors=[] if deferred else [dict(source='tmsf', stage='newhouse_detail', source_id=pid, message=message)])
                if code in {'identity_mismatch', 'invalid_target', 'missing_facts'}:
                    row.update(_property_type_result='review', _collection_errors=[],
                               _collection_issue=dict(name=identity['project_name'], source_id=pid, code=code, message=message))
            else:
                address_error = detail.pop('address_error', None)
                address_pending = detail.get('address_pending', False)
                if address_error or address_pending:
                    detail.pop('address', None)  # Q1: a truncated address never lands on the row.
                row.update(detail, property_type_captured_at=now(), property_type_error=None,
                           collection_error_code=None,
                           address_error=address_error or (previous.get('address_error') if address_pending else None),
                           _property_type_result='succeeded')
                row.update(listing_count_error=None, market_state_error=None)
                if address_error:
                    row['_collection_errors'] = [dict(source='tmsf', stage='newhouse_detail', source_id=pid,
                                                      message=f'{identity["project_name"]} {address_error}')]
                elif not address_pending:
                    row.update(address_origin='source_detail', address_checked_at=now(), address_verification_pending=False)
            yield row
    finally:
        client.close()


def fang_names(cancel, ignored):
    from src.services.fang_rentals import FangClient, parse_listing_page
    client = FangClient(timeout=20, cancel_event=cancel)
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
                        from src.services.fang_detail_cache import enrich_cached
                        enrich_cached(row, client.fetch, getattr(client, 'detail_cache', None))
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        from src.services.fang_request_policy import FangChallenge, FangTemporarilyUnavailable
                        if isinstance(exc, (FangChallenge, FangTemporarilyUnavailable)):
                            raise
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


def _check_mode(sources, mode):
    if mode not in {'all', 'retry_failed', 'continue'} or (mode in {'retry_failed', 'continue'} and sources != ['tmsf']):
        raise ValueError('不支持的采集模式')


def collect_names(store, sources, *, cancel=None, adapters=None, progress=None, mode='all', after_collect=None):
    _check_sources(sources)
    _check_mode(sources, mode)
    cancel = cancel or threading.Event()
    adapters = adapters or ADAPTERS
    report = dict(phase='running', running=True, started_at=now(), source=None, mode=mode,
                  stage='names', property_types=0, property_types_failed=0, property_types_cached=0, property_types_deferred=0,
                  new=0, existing=0, ignored=0, matched=0, pending=0, errors=[], truncated=[],
                  property_types_review=0, evidence_issues=[])
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
                        if record.get('source_kind') != 'project' and not record.get('property_type') and not record.get('property_type_checked_at'):
                            old = legacy.get(record['source_id'], {})
                            previous.update(property_type=old.get('property_type'), property_type_url=old.get('url'),
                                            property_type_captured_at=old.get('captured_at'))
                        existing[(record.get('source_kind', 'community'), str(record['source_id']))] = previous
                    kwargs['existing'] = existing
                    kwargs['retry_failed'] = mode in {'retry_failed', 'continue'}
                    kwargs['resume'] = mode == 'continue'
                for row in adapter(cancel, store.is_ignored, **kwargs):
                    check(cancel)
                    if row.pop('_errors_only', False):
                        report['stage'] = row.pop('_stage', 'names')
                        report['errors'].extend(row.pop('_collection_errors', []))
                        if progress:
                            progress(report)
                        continue
                    report['stage'] = row.pop('_stage', 'names')
                    pause_reason = row.pop('_newhouse_pause_reason', None)
                    if pause_reason in {'manual_verification', 'challenge', 'paused', 'busy',
                                        'browser_timeout', 'browser_error', 'browser_unavailable'}:
                        report.setdefault('newhouse_pause_reason', pause_reason)
                    type_result = row.pop('_property_type_result', None)
                    issue = row.pop('_collection_issue', None)
                    key = (source, row.get('source_kind', 'community'), str(row['source_id']))
                    if store.is_ignored(*key):
                        if key not in handled:
                            report['ignored'] += 1
                    else:
                        if issue:
                            report['evidence_issues'].append(issue)
                        if type_result:
                            counter = {'succeeded': 'property_types', 'failed': 'property_types_failed', 'cached': 'property_types_cached',
                                       'deferred': 'property_types_deferred', 'review': 'property_types_review'}[type_result]
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
        if report['property_types_deferred']:
            reason = report.get('newhouse_pause_reason')
            if reason in {'manual_verification', 'challenge', 'paused'}:
                advice = '请在验证冷却结束后重试（通常 15 分钟）'
            elif reason == 'busy':
                advice = '浏览器会话被占用，请在其他采集结束后重试'
            elif reason == 'browser_timeout':
                advice = '页面加载超时，请稍后重试'
            elif reason in {'browser_error', 'browser_unavailable'}:
                advice = '请检查新房浏览器服务后重试'
            else:
                advice = '请查看具体失败原因后重试'
            report['truncated'].append(dict(source='tmsf', stage='newhouse_detail',
                message=f'新房详情已暂停，本轮暂缓 {report["property_types_deferred"]} 个项目，名单已保留；{advice}'))
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
        if after_collect and not cancel.is_set() and report.get('phase') not in {'failed', 'cancelled'}:
            try:
                report['position_followup'] = after_collect(handled)
            except Exception:
                logger.exception('Could not start shared position followup')
                report['position_followup'] = {'state': 'failed', 'message': '资料已保存，主体匹配未启动，请继续匹配'}
                report['errors'].append(dict(source='amap', stage='position_followup', message='资料已保存，主体匹配未启动，请继续匹配'))
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

    def status(self):
        resolutions = {}
        for record in self.store.sources():
            if record.get('source') == 'tmsf' and record.get('status') != 'ignored':
                state = collection_resolution(record)['state']
                resolutions[state] = resolutions.get(state, 0) + 1
        return {**(self.state or {'running': False, 'phase': 'idle'}), 'resolutions': resolutions,
                'retryable': len(retryable_sources(self.store.sources())),
                'continuable': len(continuable_sources(self.store.sources()))}

    def _match_sources(self, handled):
        if self.cancel.is_set():
            return {'state': 'cancelled'}
        from src.services.address_policy_migration import enabled
        with self.store.db() as db:
            if not enabled(db):
                return {'state': 'disabled'}
        cids = sorted({r['community_id'] for r in self.store.sources()
            if (r['source'], r['source_kind'], str(r['source_id'])) in handled
            and r.get('community_id') and r.get('status') == 'matched' and r.get('property_type')
            and collection_resolution(r)['state'] in {'ready', 'position_pending'}})
        if not cids:
            return {'state': 'not_needed'}
        from src.services.directory_position import get_position_job
        try:
            get_position_job(self.store).start(community_ids=cids)
        except ValueError as exc:
            return {'state': 'pending', 'message': str(exc)}
        return {'state': 'started', 'targets': len(cids)}

    def start(self, sources, *, mode='all'):
        _check_sources(sources)
        _check_mode(sources, mode)
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError('楼盘资料采集正在运行')
            if mode in {'retry_failed', 'continue'} and not (continuable_sources(self.store.sources()) if mode == 'continue' else retryable_sources(self.store.sources())):
                raise ValueError('当前没有可重试的失败项')
            self.cancel.clear()
            self._save({'running': True, 'phase': 'running', 'mode': mode, 'started_at': now()})
            self.worker = threading.Thread(target=collect_names, args=(self.store, sources),
                kwargs={'cancel': self.cancel, 'progress': self._save, 'mode': mode,
                        'after_collect': self._match_sources}, daemon=True)
            self.worker.start()
        return self.state

    def shutdown(self):
        self.cancel.set()
        if self.worker:
            self.worker.join()
