"""Materialize TMSF identities and expose independent business queues after migration."""
import json
import uuid

from src.services.community_registry import dump, normalized, now
from src.services.community_admission import community_views, property_facts
from src.services.directory_policy import enabled, eligibility, VERSION
from src.services.directory_position_state import position_view
from src.services.tmsf_property_type import effective_market_state
from src.services.use_review_policy import use_review_projection
from src.services.use_review_scope import auto_review_skip_reason


def is_enabled(store):
    with store.db() as db:
        return enabled(db)


def synchronize(store, data_dir):
    facts = property_facts(data_dir)
    with store.db() as db:
        if not enabled(db):
            return 0
        return materialize(store, db, facts)


def materialize(store, db, facts):
    """Create only proven TMSF residential identities; preserve manual identity vetoes."""
    created = 0
    for row in db.execute("SELECT * FROM sources WHERE source='tmsf' AND status='pending' AND cid IS NULL").fetchall():
        record = store._source(row)
        if store._review_locked(db, row['id']) or db.execute('SELECT 1 FROM rejected WHERE rid=?', (row['id'],)).fetchone():
            continue
        c = dict(community_name=record['name'], district=record.get('district'), address=record.get('address'),
                 aliases=record.get('aliases', []))
        if eligibility(c, [record], facts)['admission_state'] != 'admitted':
            continue
        # A plausible existing identity needs association evidence, not another master.
        existing = [store._community(r) for r in db.execute('SELECT * FROM communities')]
        if any(normalized(record['name']) in {normalized(n) for n in [m['community_name'], m.get('community_alias'), *m.get('aliases', [])] if n}
               and normalized(record.get('district')).removesuffix('区') == normalized(m.get('district')).removesuffix('区')
               for m in existing):
            continue
        cid = 'local-' + uuid.uuid5(uuid.NAMESPACE_URL, VERSION + ':' + row['id']).hex[:16]
        c.update(community_id=cid, updated_at=now())
        db.execute('INSERT INTO communities(id,payload) VALUES (?,?)', (cid, dump(c)))
        admission = dict(state='admitted', decision_kind='automatic', revision=1, auto_review_locked=False,
                         property_type=eligibility(c, [record], facts)['effective_property_type'],
                         reason='透明售房网资料符合住宅收录条件', rule_version=VERSION, decided_at=now())
        db.execute('INSERT INTO community_admission VALUES (?,?)', (cid, dump(admission)))
        db.execute("UPDATE sources SET cid=?,status='matched',method='auto',evidence=? WHERE id=? AND status='pending'",
                   (cid, dump(['透明售房网完整住宅资料']), row['id']))
        store._event(db, cid, 'directory_auto_admit', {'record_id': row['id'], 'rule_version': VERSION})
        created += 1
    return created


def catalog_property_types(row, facts):
    """Use the same TMSF evidence as the visible catalog, including legacy facts."""
    types = set()
    for record in row.get('sources', []):
        if record.get('source') != 'tmsf':
            continue
        prop = record.get('property_type')
        if not prop and not record.get('property_type_checked_at') and record.get('source_kind') != 'project':
            prop = facts.get(str(record['source_id']), {}).get('property_type')
        if prop:
            types.add(prop)
    return sorted(types)


def inventory(store, data_dir):
    """Unlinked TMSF records are visible as incomplete/excluded entries, never auctions."""
    facts = property_facts(data_dir)
    sources = store.sources()
    views = community_views(store, data_dir)
    with store.db() as db:
        protected = {r['rid']: json.loads(r['payload']) for r in db.execute(
            'SELECT m.rid,c.payload FROM review_members m JOIN review_candidates c ON c.id=m.candidate_id')}
    output = []
    for c in views:
        records = [r for r in sources if r['community_id'] == c['community_id'] and r['status'] == 'matched']
        # Old non-TMSF identities stay in history, not the new TMSF catalog.
        if not any(r['source'] == 'tmsf' for r in records):
            continue
        output.append({**c, 'position': position_view(c, records),
                       'use_review': use_review_projection(c, records, c.get('admission'), facts),
                       'sources': [{k: v for k, v in r.items() if k != 'samples'} for r in records]})
    for r in sources:
        if r['source'] != 'tmsf' or r['status'] != 'pending' or r['community_id']:
            continue
        c = dict(community_id='source-' + r['id'], community_name=r['name'], district=r.get('district'),
                 address=r.get('address') or '', aliases=r.get('aliases', []), source_record_id=r['id'])
        decision = protected.get(r['id'], {})
        manual = {'decision_kind': 'manual', 'state': decision.get('state'), 'auto_review_locked': True, 'reason': decision.get('reason')} if decision.get('auto_review_locked') else {}
        status = eligibility(c, [r], facts, manual)
        if status['admission_state'] == 'admitted':
            status.update(admission_state='excluded', qualification='identity_pending', facts_state='incomplete',
                          exclusion_reason='小区身份存在重复或人工关联限制，待补资料')
        output.append({**c, **status, 'market_state': effective_market_state(r),
                       'use_review': use_review_projection(c, [r], manual, facts),
                       'sources': [{k: v for k, v in r.items() if k != 'samples'}], 'map_status': 'not_admitted'})
    for row in output:
        row['property_types'] = catalog_property_types(row, facts)
        row['use_review']['auto_skip_reason'] = auto_review_skip_reason(row)
    return sorted(output, key=lambda c: (c['community_name'], c['community_id']))


def admitted(store, data_dir):
    return [c for c in community_views(store, data_dir) if c['admission_state'] == 'admitted']


def auction_tasks(store, data_dir, *, include_skipped=False):
    targets = admitted(store, data_dir)
    result = []
    with store.db() as db:
        skipped = {r['key'].removeprefix('auction_skip:'): json.loads(r['value'])
                   for r in db.execute("SELECT * FROM meta WHERE key LIKE 'auction_skip:%'")}
    from src.services.auction_store import read_store
    auction_rows = read_store(data_dir / 'auction_records.json')['records']
    for r in store.sources():
        if r['source'] != 'laipai' or r['status'] == 'ignored':
            continue
        if r['status'] == 'matched' and r['community_id'] in {c['community_id'] for c in targets}:
            continue
        from src.services.community_review import fingerprint
        fp = fingerprint([r])
        is_skipped = skipped.get(r['id']) == fp
        if is_skipped and not include_skipped:
            continue
        result.append({**{k: v for k, v in r.items() if k != 'samples'}, 'revision': fp,
                       'rounds': [{k: a.get(k) for k in ('auction_id', 'title', 'round', 'source_url')} for a in auction_rows if str(a['auction_id']) in {str(i) for i in r.get('auction_ids', [])}],
                       'skipped': is_skipped, 'candidates': store.candidates(r, communities=targets),
                       'reason': '关联目标已不符合住宅条件' if r['community_id'] else '未找到唯一可靠的小区关联，请核对名称、地址和分期'})
    return result


def decide_auction(store, data_dir, rid, *, revision, action, community_id=None):
    from src.services.community_review import fingerprint
    facts = property_facts(data_dir)
    with store.db() as db:
        row = db.execute("SELECT * FROM sources WHERE id=? AND source='laipai' AND status<>'ignored'", (rid,)).fetchone()
        if not row or fingerprint([store._source(row)]) != revision:
            raise ValueError('法拍资料已变化，请刷新')
        if action == 'bind':
            c = db.execute('SELECT * FROM communities WHERE id=?', (community_id,)).fetchone()
            if not c:
                raise ValueError('请选择已收录住宅')
            members = [store._source(s) for s in db.execute("SELECT * FROM sources WHERE cid=? AND status='matched'", (community_id,))]
            a = db.execute('SELECT payload FROM community_admission WHERE cid=?', (community_id,)).fetchone()
            if eligibility(store._community(c), members, facts, json.loads(a[0]) if a else {})['admission_state'] != 'admitted':
                raise ValueError('目标必须是当前已收录住宅')
            store._associate(db, rid, community_id, review_override=True)
            db.execute('DELETE FROM meta WHERE key=?', ('auction_skip:' + rid,))
        elif action in {'skip', 'reopen'}:
            if action == 'skip':
                db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('auction_skip:' + rid, dump(revision)))
            else:
                db.execute('DELETE FROM meta WHERE key=?', ('auction_skip:' + rid,))
            store._event(db, row['cid'], 'auction_' + action, {'record_id': rid})
        else:
            raise ValueError('未知法拍关联操作')
