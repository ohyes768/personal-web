"""高德用途分类复核：不限类型查询、证据存储与批量任务。

复核只写附加的 `use_review` 证据，永不自动收录或排除；人工用途决定
独立存放在 community_admission，不受复核刷新影响。
"""
import copy
import json
import threading

from src.services.amap_directory import AmapClient
from src.services.community_admission import property_facts
from src.services.community_registry import dump, normalized, now
from src.services.directory_policy import enabled, eligibility
from src.services.directory_position_state import position_view
from src.services.use_review_scope import auto_review_skip_reason
from src.services.use_review_policy import (
    CHECKED, CONFLICT, ERROR, NOT_FOUND, RULE_VERSION, UNCERTAIN, compare, contrary_evidence,
    select_evidence, tmsf_property_types, use_identity, use_review_projection, use_review_view,
)

# 高德每页 25 条，最多可翻页取 200 条；未取完整时不采用用途证据。
MAX_PAGES = 8
# 主名没有名称匹配时，用别名重试查询的上限。
ALIAS_RETRIES = 3
# 批量任务的持久状态键与请求预算。
KEY = 'directory_use_review_job'
BUDGET = 256


class UseReviewOutcome(ValueError):
    """复核完成并已持久化结论（未找到/不确定/失败）。"""

    def __init__(self, message, state=None):
        super().__init__(message)
        self.state = state


def _read_snapshot(db, store, cid):
    master = db.execute('SELECT * FROM communities WHERE id=?', (cid,)).fetchone()
    if not master:
        raise ValueError('小区不存在')
    members = [dict(r) for r in db.execute('SELECT * FROM sources WHERE cid=? ORDER BY id', (cid,))]
    admission = db.execute('SELECT payload FROM community_admission WHERE cid=?', (cid,)).fetchone()
    return dict(master=dict(master), members=members, admission=admission[0] if admission else None)


def _snapshot(store, cid):
    with store.db() as db:
        return _read_snapshot(db, store, cid)


def _target(store, snapshot):
    """复核对象：未删除未合并、且有透明售房网资料的小区。

    手动查询保留全部真实身份；批量查询另按自动复核范围筛选。
    """
    master = snapshot['master']
    if master['deleted'] or master['merged_to']:
        raise ValueError('小区已删除或合并')
    records = [store._source(r) for r in snapshot['members'] if r['status'] == 'matched']
    if not any(r['source'] == 'tmsf' for r in records):
        raise ValueError('该小区没有透明售房网资料，无法复核用途')
    return store._community(master), records


def _retry_aliases(target):
    seen = {normalized(target.get('community_name'))}
    aliases = []
    for alias in target.get('aliases', []):
        key = normalized(alias)
        if key and key not in seen:
            seen.add(key)
            aliases.append(alias)
    return aliases[:ALIAS_RETRIES]


def _search_review(client, name, district, *, cancelled):
    """遍历可返回的分页；高德 count 可能大于实际可返回数量。"""
    pois = {}
    total = None
    for page in range(1, MAX_PAGES + 1):
        if cancelled():
            raise InterruptedError()
        options = {'types': None}
        if page > 1:
            options['page'] = page
        rows, count = client.search_name(name, district, **options)
        if cancelled():
            raise InterruptedError()
        # Zero-result searches may include a geocoding suggestion without a POI
        # identity. It is not a truncated place page and must not block aliases.
        if count == 0 and rows and all(not row.get('id') for row in rows):
            return list(pois.values()), True
        # Real Amap responses can report 53 results but return 25 + 14 + an
        # empty page whose count becomes 0. That is a terminal page, not failure.
        if not rows:
            return list(pois.values()), bool(pois) or count == 0
        total = max(total or 0, count)
        before = len(pois)
        for row in rows:
            sid = row.get('id')
            if not isinstance(sid, str) or not sid:
                return list(pois.values()), False
            pois[sid] = row
        if len(pois) == total:
            return list(pois.values()), True
        if len(pois) == before:
            break
    return list(pois.values()), False


def _publish(store, cid, snapshot, values, *, cancelled=lambda: False):
    with store.db() as db:
        if cancelled():
            raise InterruptedError()
        current = _read_snapshot(db, store, cid)
        if current != snapshot:
            raise ValueError('小区资料已变化，请重试')
        master = current['master']
        if master['deleted'] or master['merged_to']:
            raise ValueError('小区已删除或合并')
        target = store._community(master)
        if use_identity(target) != values['identity']:
            raise ValueError('小区身份已变化，请重试')
        payload = json.loads(master['payload'])
        payload['use_review'] = values
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), cid))
        store._event(db, cid, 'use_review', {'state': values['state'], 'category': values['category']})


def stored_review(store, cid):
    """当前保存的复核证据（身份指纹或规则版本不符即视为无证据）。"""
    with store.db() as db:
        row = db.execute('SELECT * FROM communities WHERE id=?', (cid,)).fetchone()
    return use_review_view(store._community(row)) if row else {}


def review_targets(store, data_dir):
    """只把需要自动核对用途的真实目录身份纳入批量查询。"""
    from src.services.directory_workflow import inventory
    return [c for c in inventory(store, data_dir) if not c.get('source_record_id')
            and not c['use_review'].get('auto_skip_reason')]


def use_review_detail(store, data_dir, cid):
    """单个小区的复核投影：证据、矩阵结论与人工决定。"""
    with store.db() as db:
        row = db.execute('SELECT * FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (cid,)).fetchone()
        if not row:
            raise ValueError('小区不存在或已删除')
        records = [store._source(r) for r in db.execute(
            "SELECT * FROM sources WHERE cid=? AND status='matched'", (cid,))]
        admission = db.execute('SELECT payload FROM community_admission WHERE cid=?', (cid,)).fetchone()
    target = store._community(row)
    admission = json.loads(admission[0]) if admission else {}
    facts = property_facts(data_dir)
    review = use_review_projection(target, records, admission, facts)
    review['auto_skip_reason'] = _auto_skip_reason(target, records, admission, facts)
    return review


def _auto_skip_reason(target, records, admission, facts):
    return auto_review_skip_reason({**target, **eligibility(target, records, facts, admission),
        'admission': admission, 'sources': records, 'position': position_view(target, records),
        'property_types': [t for t in tmsf_property_types(records, facts) if t]})


def review_outcome(target, facts, review):
    """复核后的分流结果：与透明售房网冲突、或出现新的相反证据，都需要人工审核。"""
    admission = target.get('admission') or {}
    records = [r for r in target.get('sources', []) if r.get('source') == 'tmsf']
    if admission.get('use_rule') == RULE_VERSION and admission.get('use_decision'):
        return 'conflict' if contrary_evidence(admission, records, review) else 'updated'
    types = {value for value in tmsf_property_types(records, facts) if value}
    category = review.get('category') if review.get('state') == CHECKED else None
    return 'conflict' if compare(types, category) == CONFLICT else 'updated'


def review_one(store, data_dir, cid, client=None, *, cancelled=lambda: False, force=False, automatic=False):
    """对单个小区做一次高德用途分类复核并保存证据。"""
    snapshot = _snapshot(store, cid)
    target, records = _target(store, snapshot)
    from src.services.collection_pipeline import active, selected_review
    if active(target):
        if cancelled():
            raise InterruptedError()
        if not selected_review(target, records)['state']:
            raise ValueError('请先匹配并确认高德主体地点及类型，或人工确认用途')
        # New flow classifies from the selected POI, never a second text search.
        return 'updated'
    if automatic and _auto_skip_reason(target, records,
            json.loads(snapshot['admission']) if snapshot['admission'] else {}, property_facts(data_dir)):
        return 'skipped'
    previous = use_review_view(target)
    if not force and previous['state'] == CHECKED:
        return 'skipped'
    district = (target.get('district') or '').removesuffix('区')
    values = dict(identity=use_identity(target), rule_version=RULE_VERSION, state=ERROR,
                  category=None, checked_at=now(), error=None, evidence=None, candidates_count=0)
    owned = client is None
    try:
        client = client or AmapClient()
        pois, complete = _search_review(client, target['community_name'], district, cancelled=cancelled)
        selected = select_evidence(pois, target)
        if selected['state'] == NOT_FOUND and complete:
            # 主名没有名称匹配时按别名重试；别名命中才改用别名结果。
            for alias in _retry_aliases(target):
                alias_pois, alias_complete = _search_review(client, alias, district, cancelled=cancelled)
                alias_selected = select_evidence(alias_pois, target)
                if not alias_complete or alias_selected['state'] != NOT_FOUND:
                    complete, selected = alias_complete, alias_selected
                    break
        if not complete:
            # 结果被截断，名称匹配候选无法确认，不作为任何方向的证据。
            values.update(state=UNCERTAIN, error='高德返回结果未完整，匹配不确定，待复核')
        else:
            values.update(state=selected['state'], category=selected['category'],
                          evidence=selected['evidence'], candidates_count=selected['candidates_count'])
            if selected['state'] == NOT_FOUND:
                values['error'] = '未找到名称与区域匹配的高德地点，待复核'
            elif selected['state'] == UNCERTAIN:
                values['error'] = '高德候选用途不一致，匹配不确定，待复核'
    except InterruptedError:
        raise
    except Exception as exc:
        error = str(exc) if isinstance(exc, ValueError) else '高德用途复核请求失败，请重试'
        values.update(state=ERROR, error=error)
    finally:
        if owned and client:
            client.close()
    _publish(store, cid, snapshot, values, cancelled=cancelled)
    if values['state'] == ERROR:
        raise UseReviewOutcome(values['error'], state=ERROR)
    if values['state'] in {NOT_FOUND, UNCERTAIN}:
        raise UseReviewOutcome(values['error'], state=values['state'])
    return 'updated'


class UseReviewJob:
    """批量用途复核：快照目标、请求预算、间隔限速、取消与中断续跑。"""

    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.worker = None
        with store.db() as db:
            row = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
        self.state = json.loads(row[0]) if row else None
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
                raise ValueError('高德用途复核正在进行')
            self.cancel.clear()
            self.state = self._initial_state()
            self._save()
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()
            return self.snapshot()

    @staticmethod
    def _initial_state():
        return dict(running=True, phase='running', processed=0, total=0, updated=0, conflict=0,
                    not_found=0, uncertain=0, error=0, skipped=0, requests=0, errors=[],
                    started_at=now(), finished_at=None)

    def _run(self, *, client=None, delay=2, budget=BUDGET):
        owned = client is None
        facts = property_facts(self.store.path.parent)
        with self.lock:
            if not self.state:
                self.state = self._initial_state()
        try:
            targets = review_targets(self.store, self.store.path.parent)
            with self.lock:
                self.state['total'] = len(targets)
            requests = 0
            budget_stopped = False
            for target in targets:
                if self.cancel.is_set():
                    raise InterruptedError()
                cid = target['community_id']
                if (target.get('use_review') or {}).get('state') == CHECKED:
                    outcome = 'skipped'
                else:
                    if requests >= budget:
                        with self.lock:
                            self.state['errors'].append({'message': '达到本轮请求预算，未完成目标可下次重试'})
                        budget_stopped = True
                        break
                    if requests and self.cancel.wait(delay):
                        raise InterruptedError()
                    requests += 1
                    if client is None and owned:
                        # 空跑不构造客户端，因此没有 key 也能跑完。
                        client = AmapClient()
                    try:
                        result = review_one(self.store, self.store.path.parent, cid, client,
                                            cancelled=self.cancel.is_set, automatic=True)
                    except InterruptedError:
                        raise
                    except UseReviewOutcome as exc:
                        with self.lock:
                            self.state[exc.state] += 1
                            self.state['errors'].append({'community_id': cid, 'name': target['community_name'],
                                                         'message': str(exc), 'state': exc.state})
                        outcome = None
                    except Exception as exc:
                        message = str(exc) if isinstance(exc, ValueError) else '用途复核失败，已有证据保留'
                        with self.lock:
                            self.state['error'] += 1
                            self.state['errors'].append({'community_id': cid, 'name': target['community_name'],
                                                         'message': message, 'state': ERROR})
                        outcome = None
                    else:
                        outcome = 'skipped' if result == 'skipped' else review_outcome(target, facts, stored_review(self.store, cid))
                with self.lock:
                    self.state['processed'] += 1
                    self.state['requests'] = requests
                    if outcome:
                        self.state[outcome] += 1
                self._save()
            with self.lock:
                self.state['phase'] = 'partial_failed' if (self.state['error'] or budget_stopped) else 'succeeded'
        except InterruptedError:
            with self.lock:
                self.state['phase'] = 'cancelled'
        except Exception:
            with self.lock:
                self.state['phase'] = 'failed'
                self.state['errors'].append({'message': '高德用途复核失败，请检查配置后重试'})
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
