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
        if eligibility(store._community(current['master']), records, facts,
                       json.loads(current['admission']) if current['admission'] else {})['admission_state'] != 'admitted':
            raise ValueError('小区已不符合收录条件')
        payload = json.loads(current['master']['payload'])
        target = store._community(current['master'])
        payload['amap_position'] = values
        district = (target.get('district') or '').removesuffix('区')
        # POI evidence can be completed without overwriting an existing map point.
        positioned = valid_position(target, district) or any(valid_position(r, district) for r in records) or valid_position({**historical, 'coordinate_system': historical.get('coordinate_system', 'gcj02')}, district)
        if point and (replace or not positioned):
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


def _name_matches(pois, names, district):
    """POIs whose normalized name equals or contains a community name/alias (shorter side length >= 3)."""
    matches = {}
    for raw in pois:
        p = normalize_poi(raw, district=district)
        if not p:
            continue
        name = normalized(p['name'])
        if name in names or any((len(n) >= 3 and n in name) or (len(name) >= 3 and name in n) for n in names):
            matches[p['source_id']] = p
    return matches


def position_one(store, data_dir, cid, client=None, *, cancelled=lambda: False, force=False):
    snapshot = _snapshot(store, cid)
    target = _target(store, data_dir, cid)
    records = [store._source(r) for r in snapshot['members'] if r['status'] == 'matched']
    previous = position_view(target, records)
    if previous['state'] == 'manual' or (not force and previous['state'] not in {'pending', 'error'}):
        return 'skipped'
    district = (target.get('district') or '').removesuffix('区')
    names = {normalized(n) for n in [target['community_name'], *target.get('aliases', [])] if n}
    values = dict(identity=identity(target), checked_at=now(), candidates=[])
    point = None
    error = None
    owned = client is None
    try:
        client = client or AmapClient()
        pois, count = client.search_name(target['community_name'], district)
        matches = _name_matches(pois, names, district)
        # Alias retry only when the primary name yields nothing and the result is not truncated.
        if not matches and count <= 25:
            aliases, seen = [], {normalized(target['community_name'])}
            for alias in target.get('aliases', []):
                key = normalized(alias)
                if key and key not in seen:
                    seen.add(key)
                    aliases.append(alias)
            for alias in aliases[:3]:
                alias_pois, alias_count = client.search_name(alias, district)
                alias_matches = _name_matches(alias_pois, names, district)
                if alias_matches:
                    matches, count = alias_matches, alias_count
                    break
        candidates = list(matches.values())
        # A single untruncated candidate is trusted even when the name is a containment hit
        # or the address differs; multiple candidates and truncation stay review.
        if count <= 25 and len(candidates) == 1:
            point = candidates[0]
            values.update(state='matched', selected=point, candidates=candidates)
        elif candidates or count > 25:
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
            targets = [c for c in inventory(self.store, self.store.path.parent) if c['admission_state'] == 'admitted']
            with self.lock:
                self.state['total'] = len(targets)
            requests = 0
            budget_stopped = False
            for target in targets:
                if self.cancel.is_set():
                    raise InterruptedError()
                cid = target['community_id']
                current_state = position_view(target, target.get('sources', [])).get('state')
                if current_state not in {'pending', 'error'}:
                    outcome = 'skipped'
                    with self.lock:
                        by = self.state['skipped_by_state']
                        by[current_state] = by.get(current_state, 0) + 1
                else:
                    if requests >= budget:
                        with self.lock:
                            self.state['errors'].append({'message': '达到本轮请求预算，未完成目标可下次重试'})
                        budget_stopped = True
                        break
                    if requests and self.cancel.wait(delay):
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
