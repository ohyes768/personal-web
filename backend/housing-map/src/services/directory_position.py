"""Bounded Amap enrichment for admitted identities, independent of TMSF collection."""
import copy
import json
import threading

from src.services.community_registry import dump, normalized, now
from src.services.community_admission import property_facts
from src.services.community_enrichment import valid_position, qualified_address
from src.services.directory_policy import enabled, eligibility
from src.services.directory_workflow import admitted
from src.services.amap_directory import AmapClient, normalize_poi

KEY = 'directory_position_job'


def keep_position(target):
    district = (target.get('district') or '').removesuffix('区')
    return (target.get('coordinate_evidence', {}).get('source') == 'manual' or target.get('coordinate_origin') == 'manual'
            or (valid_position(target, district) and not target.get('coordinate_conflict')))


def position_one(store, data_dir, cid, client, *, cancelled=lambda: False):
    """Publish only if the entire identity and its admission still match the read snapshot."""
    target = next((c for c in admitted(store, data_dir) if c['community_id'] == cid), None)
    if not target:
        raise ValueError('小区已不符合收录条件')
    district = (target.get('district') or '').removesuffix('区')
    if keep_position(target):
        return 'skipped'
    with store.db() as db:
        master = dict(db.execute('SELECT * FROM communities WHERE id=?', (cid,)).fetchone())
        members = [dict(r) for r in db.execute("SELECT * FROM sources WHERE cid=? ORDER BY id", (cid,))]
        admission = db.execute('SELECT payload FROM community_admission WHERE cid=?', (cid,)).fetchone()
        admission_payload = admission[0] if admission else None
    names = {normalized(n) for n in [target['community_name'], *target.get('aliases', [])] if n}
    pois, count = client.search_name(target['community_name'], district)
    matches = {}
    for raw in pois:
        p = normalize_poi(raw, district=district)
        if not p or normalized(p['name']) not in names:
            continue
        actual = target.get('address')
        if actual and normalized(qualified_address(actual, district)) != normalized(qualified_address(p.get('address'), district)):
            continue
        matches[p['source_id']] = p
    if count > 25 or len(matches) != 1:
        raise ValueError('未找到唯一可靠位置，请核对名称、地址或分期')
    point = next(iter(matches.values()))
    if cancelled():
        raise InterruptedError()
    facts = property_facts(data_dir)
    with store.db() as db:
        current = db.execute('SELECT * FROM communities WHERE id=?', (cid,)).fetchone()
        current_members = [dict(r) for r in db.execute('SELECT * FROM sources WHERE cid=? ORDER BY id', (cid,))]
        a = db.execute('SELECT payload FROM community_admission WHERE cid=?', (cid,)).fetchone()
        if not current or dict(current) != master or current_members != members or (a[0] if a else None) != admission_payload:
            raise ValueError('小区资料或人工位置已变化，请重试')
        records = [store._source(r) for r in db.execute("SELECT * FROM sources WHERE cid=? AND status='matched'", (cid,))]
        if eligibility(store._community(current), records, facts, json.loads(a[0]) if a else {})['admission_state'] != 'admitted':
            raise ValueError('小区已不符合收录条件')
        payload = json.loads(current['payload'])
        payload.update({k: point[k] for k in ('longitude', 'latitude', 'coordinate_system')})
        payload.update(geographic_address=qualified_address(point.get('address'), district), coordinate_evidence={
            'source': 'amap', 'source_id': point['source_id'], 'source_url': point['source_url'], 'captured_at': now()},
            coordinate_error=None)
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), cid))
        store._event(db, cid, 'amap_position', {'poi_id': point['source_id']})
    return 'updated'


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
                              errors=[], started_at=now(), finished_at=None)
            self._save()
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()
            return self.snapshot()

    def _run(self, *, client=None, delay=2, budget=256):
        owned = client is None
        try:
            targets = admitted(self.store, self.store.path.parent)
            with self.lock:
                self.state['total'] = len(targets)
            requests = 0
            for target in targets:
                if self.cancel.is_set():
                    raise InterruptedError()
                cid = target['community_id']
                if keep_position(target):
                    outcome = 'skipped'
                else:
                    if requests >= budget:
                        with self.lock:
                            self.state['errors'].append({'message': '达到本轮请求预算，未完成目标可下次重试'})
                        break
                    if requests and self.cancel.wait(delay):
                        raise InterruptedError()
                    requests += 1
                    try:
                        client = client or AmapClient()
                        outcome = position_one(self.store, self.store.path.parent, cid, client, cancelled=self.cancel.is_set)
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        message = str(exc) if isinstance(exc, ValueError) else '地图查询失败，已有位置保留'
                        with self.lock:
                            self.state['errors'].append({'community_id': cid, 'name': target['community_name'], 'message': message})
                        outcome = None
                with self.lock:
                    self.state['processed'] += 1
                    if outcome:
                        self.state[outcome] += 1
                self._save()
            with self.lock:
                self.state['phase'] = 'partial_failed' if self.state['errors'] else 'succeeded'
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
