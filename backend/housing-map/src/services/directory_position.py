"""Bounded Amap enrichment for admitted identities, independent of TMSF collection."""
import copy
import hashlib
import json
import threading

from src.services.community_registry import dump, normalized, now
from src.services.community_address import valid_address
from src.services.directory_position_state import identity, position_view
from src.services.community_admission import property_facts
from src.services.community_enrichment import valid_position, qualified_address, read_json
from src.services.directory_policy import enabled, eligibility
from src.services.directory_workflow import admitted
from src.services.amap_directory import AmapClient, normalize_poi
from src.services.poi_names import flat_name, name_hit

KEY = 'directory_position_job'
_jobs = {}
_jobs_lock = threading.Lock()


def get_position_job(store):
    """Collection followups and API buttons share the same per-registry lock/job."""
    key = str(store.path.resolve())
    with _jobs_lock:
        if key not in _jobs:
            _jobs[key] = PositionJob(store)
        return _jobs[key]


class PositionOutcome(ValueError):
    """A query finished and its review/failure outcome was durably saved."""

    def __init__(self, message, state=None, reason=None):
        super().__init__(message)
        self.state = state
        self.reason = reason


def _snapshot(store, cid):
    with store.db() as db:
        return _read_snapshot(db, cid)


def _read_snapshot(db, cid):
    master = db.execute('SELECT * FROM communities WHERE id=?', (cid,)).fetchone()
    if not master:
        raise ValueError('小区不存在')
    members = [dict(r) for r in db.execute('SELECT * FROM sources WHERE cid=? ORDER BY id', (cid,))]
    admission = db.execute('SELECT payload FROM community_admission WHERE cid=?', (cid,)).fetchone()
    return dict(master=dict(master), members=members, admission=admission[0] if admission else None)


def _revision(snapshot):
    return hashlib.sha256(dump(snapshot).encode()).hexdigest()


def _target(store, data_dir, cid):
    from src.services.collection_pipeline import active
    with store.db() as db:
        row = db.execute('SELECT * FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (cid,)).fetchone()
        if row and active(store._community(row)):
            records = [store._source(r) for r in db.execute("SELECT * FROM sources WHERE cid=? AND status='matched'", (cid,))]
            if any(r['source'] == 'tmsf' for r in records):
                return store._community(row)
    target = next((c for c in admitted(store, data_dir) if c['community_id'] == cid), None)
    if not target:
        raise ValueError('小区已不符合收录条件')
    return target


def _publish(store, data_dir, cid, snapshot, values, point=None, *, replace=False, cancelled=lambda: False):
    facts = property_facts(data_dir)
    historical = read_json(store.path.parent / 'binjiang_coordinates.json').get(cid, {})
    with store.db() as db:
        if cancelled():
            raise InterruptedError()
        current = _read_snapshot(db, cid)
        if current != snapshot:
            raise ValueError('小区资料或人工位置已变化，请重试')
        records = [store._source(r) for r in current['members'] if r['status'] == 'matched']
        from src.services.collection_pipeline import active
        if not active(store._community(current['master'])) and eligibility(store._community(current['master']), records, facts,
                       json.loads(current['admission']) if current['admission'] else {})['admission_state'] != 'admitted':
            raise ValueError('小区已不符合收录条件')
        payload = json.loads(current['master']['payload'])
        target = store._community(current['master'])
        payload['amap_position'] = values
        district = (target.get('district') or '').removesuffix('区')
        # POI evidence can be completed without overwriting an existing map point.
        positioned = valid_position(target, district) or any(valid_position(r, district) for r in records) or valid_position({**historical, 'coordinate_system': historical.get('coordinate_system', 'gcj02')}, district)
        replace_automatic = active(target) and target.get('coordinate_origin') != 'manual' and (target.get('coordinate_evidence') or {}).get('source') != 'manual'
        if point and (replace or not positioned or replace_automatic):
            payload.update({k: point[k] for k in ('longitude', 'latitude', 'coordinate_system')})
            payload.update(geographic_address=qualified_address(point.get('address'), district),
                           coordinate_evidence=dict(source='manual' if values['state'] == 'manual' else 'amap',
                               source_id=point.get('source_id'), source_url=point.get('source_url'), captured_at=now()),
                           coordinate_error=None)
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), cid))
        store._event(db, cid, 'amap_position', {'state': values['state'], 'poi_id': (point or {}).get('source_id')})


def position_detail(store, data_dir, cid):
    snapshot = _snapshot(store, cid)
    target = _target(store, data_dir, cid)
    if _snapshot(store, cid) != snapshot:
        raise ValueError('小区资料已变化，请刷新')
    records = [store._source(r) for r in snapshot['members'] if r['status'] == 'matched']
    return {**position_view(target, records), 'revision': _revision(snapshot)}


_flat_name = flat_name


def _valid_pois(pois, district):
    """All in-district, category-whitelisted, non-attached POIs keyed by source_id."""
    valid = {}
    for raw in pois:
        p = normalize_poi(raw, district=district)
        if p:
            valid[p['source_id']] = p
    return valid


def _name_hit(p, flats):
    """Whether a normalized POI's flattened name equals or contains a flattened
    community name/alias (shorter side length >= 3); comparison ignores dots,
    suffixes and parentheticals."""
    return name_hit(p['name'], flats)


def query_unqueried(view):
    """No usable query or history exists for this identity."""
    return (view.get('state') == 'pending' and not view.get('checked_at')
            and not view.get('query_history'))


def query_retryable(view):
    """Only actual failures/incomplete results, never budget stops or ambiguity."""
    if view.get('review_reason') == 'request_budget' or '请求预算' in (view.get('error') or ''):
        return False
    return (view.get('state') == 'error' or
            (view.get('state') == 'review' and view.get('review_reason') == 'results_incomplete') or
            (view.get('state') == 'pending' and (view.get('query_history') or {}).get('state') in {'error', 'incomplete'}))


def query_continuable(view):
    return (query_unqueried(view) or query_retryable(view)
            or (view.get('state') == 'pending' and (view.get('query_history') or {}).get('state') == 'stale')
            or view.get('review_reason') == 'request_budget'
            or '请求预算' in (view.get('error') or '')) and view.get('state') != 'manual'


def batch_targets(store):
    from src.services.directory_workflow import inventory
    from src.services.collection_pipeline import active
    return [c for c in inventory(store, store.path.parent)
            if (c['admission_state'] == 'admitted' or active(c)) and not c.get('source_record_id')
            and (not active(c) or (c.get('workflow_state') != 'excluded'
                                  and c['qualification'] not in {'non_residential', 'manual_exclusion', 'region_conflict'}
                                  and not (c.get('use_review') or {}).get('auto_skip_reason')))]


def position_one(store, data_dir, cid, client=None, *, cancelled=lambda: False, force=False, automatic=False,
                 retry_failed_only=False):
    snapshot = _snapshot(store, cid)
    target = _target(store, data_dir, cid)
    from src.services.collection_pipeline import active, subject_name, subject_pois
    pipeline = active(target)
    records = [store._source(r) for r in snapshot['members'] if r['status'] == 'matched']
    previous = position_view(target, records)
    if automatic and pipeline:
        from src.services.use_review_scope import auto_review_skip_reason
        from src.services.use_review_policy import tmsf_property_types
        facts = property_facts(data_dir)
        admission = json.loads(snapshot['admission']) if snapshot['admission'] else {}
        status = eligibility(target, records, facts, admission)
        fresh = {**target, **status, 'admission': admission, 'sources': records, 'position': previous,
                 'property_types': tmsf_property_types(records, facts)}
        if status.get('workflow_state') == 'excluded' or auto_review_skip_reason(fresh):
            return 'skipped'
    if retry_failed_only and not query_retryable(previous):
        return 'skipped'
    from src.services.collection_pipeline import selected_review
    needs_subject_type = pipeline and previous['state'] == 'matched' and not selected_review(target, records)['state']
    if previous['state'] == 'manual' or (not force and previous['state'] not in {'pending', 'error'}
                                        and not needs_subject_type and not query_retryable(previous)):
        return 'skipped'
    district = (target.get('district') or '').removesuffix('区')
    names = {normalized(n) for n in [target['community_name'], *target.get('aliases', [])] if n}
    values = dict(identity=identity(target), checked_at=now(), candidates=[])
    point = None
    error = None
    owned = client is None
    try:
        client = client or AmapClient()
        def lookup(name):
            if pipeline:
                from src.services.directory_use_review import _search_review
                rows, complete = _search_review(client, name, district, cancelled=cancelled)
                return rows, len(rows) if complete else max(26, len(rows)), complete
            rows, total = client.search_name(name, district)
            return rows, total, total <= 25
        pois, count, complete = lookup(target['community_name'])
        valid = subject_pois(pois, district) if pipeline else _valid_pois(pois, district)
        if pipeline:
            from src.services.collection_pipeline import reference_pois
            references = {p['source_id']: p for p in reference_pois(pois, district, names, valid)}
        flats = {_flat_name(n) for n in names}
        precise_names = {subject_name(n) for n in names}
        def is_match(p):
            return subject_name(p['name']) in precise_names if pipeline else _name_hit(p, flats)
        matches = {k: p for k, p in valid.items() if is_match(p)}
        # Alias retry only when the primary name yields nothing and the result is not truncated.
        if not matches and complete:
            aliases, seen = [], {normalized(target['community_name'])}
            for alias in target.get('aliases', []):
                key = normalized(alias)
                if key and key not in seen:
                    seen.add(key)
                    aliases.append(alias)
            for alias in aliases[:3]:
                alias_pois, alias_count, alias_complete = lookup(alias)
                alias_valid = subject_pois(alias_pois, district) if pipeline else _valid_pois(alias_pois, district)
                if pipeline:
                    references.update({p['source_id']: p for p in reference_pois(alias_pois, district, names, alias_valid)})
                alias_matches = {k: p for k, p in alias_valid.items() if is_match(p)}
                if alias_matches:
                    valid, matches, count, complete = alias_valid, alias_matches, alias_count, alias_complete
                    break
        if pipeline:
            values['reference_candidates'] = list(references.values())
        # In-district POIs failing the name check stay visible as suspect candidates
        # for human confirmation; they never qualify for auto-binding.
        suspects = {k: p for k, p in valid.items() if k not in matches}
        for p in matches.values():
            p['name_matched'] = True
        for p in suspects.values():
            p['name_matched'] = False
        candidates = [*matches.values(), *suspects.values()]
        if len(candidates) > 1:
            # Review queue renders most-similar first; the score is evidence for the
            # human, never an auto-bind (single-candidate trust rule is unchanged).
            from src.services.name_similarity import name_similarity
            names_for_score = [n for n in [target['community_name'], *target.get('aliases', [])] if n]
            for candidate in candidates:
                candidate['name_similarity'] = round(max(
                    (name_similarity(n, candidate.get('name') or '') for n in names_for_score), default=0.0), 4)
            candidates.sort(key=lambda p: -p['name_similarity'])
        # A single untruncated name-matched candidate is trusted even when the name is a
        # containment hit or the address differs; suspects never count toward auto-binding,
        # and truncation stays review.
        auto_subject = complete and len(matches) == 1
        if pipeline and auto_subject:
            from src.services.collection_pipeline import auto_subject_reliable
            auto_subject = auto_subject_reliable(target, next(iter(matches.values())), records)
        if auto_subject:
            point = next(iter(matches.values()))
            values.update(state='matched', selected=point, candidates=list(matches.values()))
        elif candidates or not complete:
            reason = ('results_incomplete' if not complete else 'multiple_subjects' if len(matches) > 1
                      else 'name_mismatch' if not matches else 'address_check')
            messages = {
                'results_incomplete': '高德结果尚未取完整，请重新查询后确认地点',
                'multiple_subjects': f'找到 {len(matches)} 个同名主体地点，请核对地址并选择',
                'name_mismatch': '已找到候选地点，但名称未完全对应，请核对后选择',
                'address_check': '已找到同名地点，但地址缺失或与来源门牌不同，请核对后确认',
            }
            values.update(state='review', candidates=candidates,
                          review_reason=reason, error=messages[reason] if pipeline else
                          '未找到唯一可靠位置：候选有歧义、地址不同或结果未完整返回，请核对后确认')
        else:
            values.update(state='not_found', error='未找到名称、区域及分类可靠的高德地点')
    except Exception as exc:
        if isinstance(exc, InterruptedError):
            raise
        error = str(exc) if isinstance(exc, ValueError) else '高德位置查询失败，请重试'
        from src.services.collection_pipeline import RequestBudgetExhausted
        values.update(state='pending' if isinstance(exc, RequestBudgetExhausted) else 'error', error=error)
        if isinstance(exc, RequestBudgetExhausted):
            values['review_reason'] = 'request_budget'
    finally:
        if owned and client:
            client.close()
    if previous['state'] == 'matched' and values['state'] != 'matched':
        values.update(state='matched', selected=previous['selected'], error=values.get('error') or '本次未匹配，保留已有结果')
    _publish(store, data_dir, cid, snapshot, values, point, cancelled=cancelled)
    if error:
        raise PositionOutcome(error, reason=values.get('review_reason'))
    if values['state'] in {'review', 'not_found'}:
        raise PositionOutcome(values['error'], state=values['state'], reason=values.get('review_reason'))
    return 'updated'


def confirm_position(store, data_dir, cid, *, revision, poi_id=None, longitude=None, latitude=None, address=None,
                     coordinates_verified=False):
    snapshot = _snapshot(store, cid)
    if _revision(snapshot) != revision:
        raise ValueError('定位资料已变化，请刷新后确认')
    target = _target(store, data_dir, cid)
    state = position_view(target)
    district = (target.get('district') or '').removesuffix('区')
    if poi_id:
        point = next((p for p in state.get('candidates', []) if p['source_id'] == poi_id), None)
        if not point:
            raise ValueError('候选已失效，请重新查询')
        if not valid_address(point.get('address')) and coordinates_verified is not True:
            raise ValueError('候选缺少地图地址，请先核对地图坐标并确认')
        if (point.get('district') != district or not valid_position(point, district)
                or not in_district(point, district)):
            raise ValueError('候选坐标无效或不在当前区域，请重新查询')
    else:
        point = dict(longitude=longitude, latitude=latitude, coordinate_system='gcj02', address=address)
        if not valid_address(address) or not valid_position(point, district) or not in_district(point, district):
            raise ValueError('请填写有效地图地址与区域内GCJ02坐标')
    values = dict(identity=identity(target), state='manual', checked_at=state.get('checked_at'), selected=point,
                  candidates=state.get('candidates', []), confirmed_at=now())
    if poi_id and not valid_address(point.get('address')):
        values['coordinates_verified'] = True
    _publish(store, data_dir, cid, snapshot, values, point, replace=True)
    return position_detail(store, data_dir, cid)


def in_district(point, district):
    from src.core.boundary import is_in_binjiang, is_in_xiaoshan_border
    return is_in_binjiang(point['longitude'], point['latitude']) if district == '滨江' else (
        district == '萧山' and is_in_xiaoshan_border(point['longitude'], point['latitude']))


class PositionJob:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.worker = None
        with store.db() as db:
            r = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
        self.state = json.loads(r[0]) if r else None
        if self.state and self.state.get('running'):
            self.state.update(running=False, phase='interrupted', finished_at=now())
            self._save()

    def snapshot(self):
        with self.lock:
            value = copy.deepcopy(self.state) if self.state else dict(running=False, phase='idle')
        targets = batch_targets(self.store)
        value['unqueried'] = sum(query_unqueried(c['position']) for c in targets)
        value['retryable'] = sum(query_retryable(c['position']) for c in targets)
        value['continuable'] = sum(query_continuable(c['position']) for c in targets)
        return value

    def _save(self):
        with self.lock, self.store.db() as db:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, dump(self.state)))

    def start(self, mode='all', *, community_ids=None):
        if mode not in {'all', 'refresh_all', 'unqueried', 'retry_failed', 'continue'}:
            raise ValueError('未知高德匹配模式')
        with self.lock:
            with self.store.db() as db:
                if not enabled(db):
                    raise ValueError('请先完成名单流程迁移')
            if self.worker and self.worker.is_alive():
                raise ValueError('高德信息正在采集')
            self.cancel.clear()
            self.state = dict(running=True, phase='running', processed=0, total=0, updated=0, skipped=0,
                              review=0, not_found=0, failed=0, incomplete=0, skipped_by_state={},
                              errors=[], mode=mode, started_at=now(), finished_at=None)
            self._save()
            self.worker = threading.Thread(target=self._run, kwargs={'mode': mode, 'community_ids': community_ids}, daemon=True)
            self.worker.start()
            return self.snapshot()

    def _run(self, *, client=None, delay=2, budget=None, mode='all', community_ids=None):
        owned = client is None
        try:
            from src.services.collection_pipeline import active
            targets = batch_targets(self.store)
            if community_ids is not None:
                targets = [c for c in targets if c['community_id'] in community_ids]
            if mode == 'continue':
                targets = [c for c in targets if query_continuable(c['position'])]
            if mode == 'unqueried':
                targets = [c for c in targets if query_unqueried(c['position'])]
            if mode == 'retry_failed':
                targets = [c for c in targets if query_retryable(c['position'])]
            from src.services.collection_pipeline import RequestBudgetClient
            page_client = None
            if any(active(c) for c in targets):
                supplied = client
                page_client = RequestBudgetClient(lambda: supplied or AmapClient(), limit=budget, delay=delay, cancel=self.cancel)
                client = page_client
            with self.lock:
                self.state['total'] = len(targets)
                self.state['mode'] = mode
            requests = 0
            budget_stopped = False
            for target in targets:
                if self.cancel.is_set():
                    raise InterruptedError()
                cid = target['community_id']
                current_state = position_view(target, target.get('sources', [])).get('state')
                needs_subject_type = active(target) and current_state == 'matched' and not (target.get('use_review') or {}).get('state')
                if current_state == 'manual' or (mode != 'refresh_all' and current_state not in {'pending', 'error'}
                        and not needs_subject_type and not query_retryable(target['position'])
                        and not (mode == 'continue' and query_continuable(target['position']))):
                    outcome = 'skipped'
                    with self.lock:
                        by = self.state['skipped_by_state']
                        by[current_state] = by.get(current_state, 0) + 1
                else:
                    if budget is not None and (page_client.used if page_client else requests) >= budget:
                        with self.lock:
                            self.state['errors'].append({'message': '达到本轮请求预算，未完成目标可下次重试'})
                        budget_stopped = True
                        break
                    if not page_client and requests and self.cancel.wait(delay):
                        raise InterruptedError()
                    requests += 1
                    try:
                        outcome = position_one(self.store, self.store.path.parent, cid, client,
                                               cancelled=self.cancel.is_set, automatic=True,
                                               force=mode == 'refresh_all' or (mode == 'continue' and query_continuable(target['position'])),
                                               retry_failed_only=mode == 'retry_failed')
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        message = str(exc) if isinstance(exc, ValueError) else '地图查询失败，已有位置保留'
                        if isinstance(exc, PositionOutcome) and exc.reason == 'request_budget':
                            with self.lock:
                                self.state['requests'] = page_client.used if page_client else requests
                                self.state['errors'].append({'community_id': cid, 'name': target['community_name'],
                                                             'message': message, 'reason': 'request_budget'})
                            budget_stopped = True
                            break
                        with self.lock:
                            if isinstance(exc, PositionOutcome) and exc.reason == 'results_incomplete':
                                self.state['incomplete'] = self.state.get('incomplete', 0) + 1
                            elif isinstance(exc, PositionOutcome) and exc.state:
                                self.state[exc.state] += 1
                            else:
                                self.state['failed'] += 1
                            self.state['errors'].append({'community_id': cid, 'name': target['community_name'],
                                                         'message': message, 'state': getattr(exc, 'state', None) or 'error',
                                                         'reason': getattr(exc, 'reason', None)})
                        outcome = None
                with self.lock:
                    if page_client:
                        requests = page_client.used
                        self.state['requests'] = requests
                    self.state['processed'] += 1
                    if outcome:
                        self.state[outcome] += 1
                self._save()
            with self.lock:
                self.state['phase'] = ('partial_failed' if self.state['failed'] or self.state.get('incomplete') else
                                       'budget_exhausted' if budget_stopped else 'succeeded')
        except InterruptedError:
            with self.lock:
                self.state['phase'] = 'cancelled'
        except Exception:
            with self.lock:
                self.state['phase'] = 'failed'
                self.state['errors'].append({'message': '高德信息采集失败，请检查配置后重试'})
        finally:
            if owned and client:
                client.close()
            with self.lock:
                self.state.update(running=False, finished_at=now())
            self._save()

    def shutdown(self):
        self.cancel.set()
        if self.worker:
            self.worker.join(timeout=30)
