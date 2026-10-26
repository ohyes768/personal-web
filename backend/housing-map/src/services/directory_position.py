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


class PositionOutcome(ValueError):
    """A query finished and its review/failure outcome was durably saved."""

    def __init__(self, message, state=None):
        super().__init__(message)
        self.state = state


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


def position_one(store, data_dir, cid, client=None, *, cancelled=lambda: False, force=False):
    snapshot = _snapshot(store, cid)
    target = _target(store, data_dir, cid)
    from src.services.collection_pipeline import active, subject_name, subject_pois
    pipeline = active(target)
    records = [store._source(r) for r in snapshot['members'] if r['status'] == 'matched']
    previous = position_view(target, records)
    from src.services.collection_pipeline import selected_review
    needs_subject_type = pipeline and previous['state'] == 'matched' and not selected_review(target, records)['state']
    if previous['state'] == 'manual' or (not force and previous['state'] not in {'pending', 'error'} and not needs_subject_type):
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
                alias_matches = {k: p for k, p in alias_valid.items() if is_match(p)}
                if alias_matches:
                    valid, matches, count, complete = alias_valid, alias_matches, alias_count, alias_complete
                    break
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
            values.update(state='review', candidates=candidates,
                          error='未找到唯一可靠位置：候选有歧义、地址不同或结果未完整返回，请核对后确认')
        else:
            values.update(state='not_found', error='未找到名称、区域及分类可靠的高德地点')
    except Exception as exc:
        if isinstance(exc, InterruptedError):
            raise
        error = str(exc) if isinstance(exc, ValueError) else '高德位置查询失败，请重试'
        values.update(state='error', error=error)
    finally:
        if owned and client:
            client.close()
    if previous['state'] == 'matched' and values['state'] != 'matched':
        values.update(state='matched', selected=previous['selected'], error=values.get('error') or '本次未匹配，保留已有结果')
    _publish(store, data_dir, cid, snapshot, values, point, cancelled=cancelled)
    if error:
        raise PositionOutcome(error)
    if values['state'] in {'review', 'not_found'}:
        raise PositionOutcome(values['error'], state=values['state'])
    return 'updated'


def confirm_position(store, data_dir, cid, *, revision, poi_id=None, longitude=None, latitude=None, address=None):
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
        if not valid_address(point.get('address')):
            raise ValueError('候选缺少地图地址，请核对后使用手动定位')
    else:
        point = dict(longitude=longitude, latitude=latitude, coordinate_system='gcj02', address=address)
        if not valid_address(address) or not valid_position(point, district) or not in_district(point, district):
            raise ValueError('请填写有效地图地址与区域内GCJ02坐标')
    values = dict(identity=identity(target), state='manual', checked_at=state.get('checked_at'), selected=point,
                  candidates=state.get('candidates', []), confirmed_at=now())
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
            return copy.deepcopy(self.state)

    def _save(self):
        with self.lock, self.store.db() as db:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, dump(self.state)))

    def start(self):
        with self.lock:
            with self.store.db() as db:
                if not enabled(db):
                    raise ValueError('请先完成名单流程迁移')
            if self.worker and self.worker.is_alive():
                raise ValueError('高德信息正在采集')
            self.cancel.clear()
            self.state = dict(running=True, phase='running', processed=0, total=0, updated=0, skipped=0,
                              review=0, not_found=0, failed=0, skipped_by_state={},
                              errors=[], started_at=now(), finished_at=None)
            self._save()
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()
            return self.snapshot()

    def _run(self, *, client=None, delay=2, budget=256):
        owned = client is None
        try:
            from src.services.directory_workflow import inventory
            from src.services.collection_pipeline import active
            targets = [c for c in inventory(self.store, self.store.path.parent)
                       if (c['admission_state'] == 'admitted' or active(c)) and not c.get('source_record_id')
                       and (not active(c) or (c['qualification'] not in {'non_residential', 'manual_exclusion', 'region_conflict'}
                                             and not (c.get('use_review') or {}).get('auto_skip_reason')))]
            from src.services.collection_pipeline import RequestBudgetClient
            page_client = None
            if any(active(c) for c in targets):
                supplied = client
                page_client = RequestBudgetClient(lambda: supplied or AmapClient(), limit=budget, delay=delay, cancel=self.cancel)
                client = page_client
            with self.lock:
                self.state['total'] = len(targets)
            requests = 0
            budget_stopped = False
            for target in targets:
                if self.cancel.is_set():
                    raise InterruptedError()
                cid = target['community_id']
                current_state = position_view(target, target.get('sources', [])).get('state')
                needs_subject_type = active(target) and current_state == 'matched' and not (target.get('use_review') or {}).get('state')
                if current_state not in {'pending', 'error'} and not needs_subject_type:
                    outcome = 'skipped'
                    with self.lock:
                        by = self.state['skipped_by_state']
                        by[current_state] = by.get(current_state, 0) + 1
                else:
                    if (page_client.used if page_client else requests) >= budget:
                        with self.lock:
                            self.state['errors'].append({'message': '达到本轮请求预算，未完成目标可下次重试'})
                        budget_stopped = True
                        break
                    if not page_client and requests and self.cancel.wait(delay):
                        raise InterruptedError()
                    requests += 1
                    try:
                        outcome = position_one(self.store, self.store.path.parent, cid, client, cancelled=self.cancel.is_set)
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        message = str(exc) if isinstance(exc, ValueError) else '地图查询失败，已有位置保留'
                        with self.lock:
                            if isinstance(exc, PositionOutcome) and exc.state:
                                self.state[exc.state] += 1
                            else:
                                self.state['failed'] += 1
                            self.state['errors'].append({'community_id': cid, 'name': target['community_name'],
                                                         'message': message, 'state': getattr(exc, 'state', None) or 'error'})
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
                self.state['phase'] = 'partial_failed' if (self.state['failed'] or budget_stopped) else 'succeeded'
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
