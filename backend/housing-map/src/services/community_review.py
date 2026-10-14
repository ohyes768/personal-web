"""Stable, conservative community review groups. All decisions share registry transactions."""
import hashlib
import json
import math
import uuid
from pathlib import Path

from src.services.community_admission import community_views, property_facts
from src.services.community_registry import dump, normalized, now


def same_community(a, b):
    if a.get('auto_association_disabled') or b.get('auto_association_disabled'):
        return False
    if not normalized(a.get('name')) or normalized(a.get('name')) != normalized(b.get('name')):
        return False
    district = normalized(a.get('district')).removesuffix('区')
    if not district or district != normalized(b.get('district')).removesuffix('区'):
        return False
    if a.get('address') and b.get('address'):
        return normalized(a['address']) == normalized(b['address'])
    if a.get('coordinate_system') != 'gcj02' or b.get('coordinate_system') != 'gcj02':
        return False
    values = [a.get('longitude'), a.get('latitude'), b.get('longitude'), b.get('latitude')]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        return False
    dx = (values[0] - values[2]) * math.cos(math.radians(values[1])) * 111320
    return math.hypot(dx, (values[1] - values[3]) * 111320) <= 100


def fingerprint(records, admission=None):
    ignored = {'updated_at', 'property_type_checked_at', 'property_type_captured_at'}
    payload = [{k: v for k, v in r.items() if k not in ignored} for r in sorted(records, key=lambda r: r['id'])]
    return hashlib.sha256(dump([payload, admission]).encode()).hexdigest()


def matches_filters(name, address, district, members, *, q='', area='', source='', aliases=()):
    text = ' '.join([name, address or '', *aliases, *[m['name'] for m in members]])
    return ((not area or (district or '').removesuffix('区') == area.removesuffix('区'))
            and (not source or any(m['source'] == source for m in members))
            and q.casefold() in text.casefold())


def community_matches(community, members, *, q='', district='', source='', property_type=''):
    return ((not property_type or community.get('effective_property_type') == property_type)
            and matches_filters(community['community_name'], community.get('address'), community.get('district'),
                                members, q=q, area=district, source=source, aliases=community.get('aliases', [])))


def review_matches(review, *, q='', district='', source=''):
    return matches_filters(review['name'], review.get('address'), review.get('district'), review['members'],
                           q=q, area=district, source=source)


class ReviewWorkspace:
    def __init__(self, store, data_dir):
        self.store, self.data_dir = store, Path(data_dir)

    @staticmethod
    def _save(db, item):
        db.execute('INSERT OR REPLACE INTO review_candidates VALUES (?,?)', (item['id'], dump(item)))

    @staticmethod
    def _all(db):
        return {r['id']: json.loads(r['payload']) for r in db.execute('SELECT * FROM review_candidates ORDER BY id')}

    def refresh(self):
        # Build projections, then verify their source/admission snapshot under the writer transaction.
        views = community_views(self.store, self.data_dir)
        with self.store.db() as db:
            db.execute("INSERT OR IGNORE INTO meta VALUES ('review_schema_version','1')")
            sources = {r['id']: self.store._source(r) for r in db.execute('SELECT * FROM sources ORDER BY source,kind,sid,id')}
            groups = self._all(db)
            membership = {r['rid']: r['candidate_id'] for r in db.execute('SELECT * FROM review_members')}
            masters = {c['community_id']: c for c in views}
            for cid, community in masters.items():
                rid = 'master-' + cid
                saved = groups.get(rid)
                admission_row = db.execute('SELECT payload FROM community_admission WHERE cid=?', (cid,)).fetchone()
                current_admission = json.loads(admission_row[0]) if admission_row else self.store.pending_admission()
                if current_admission != community['admission']:
                    raise ValueError('目录审核版本已变化，请刷新')
                state = community['admission_state']
                if state == 'admitted':
                    if saved:
                        saved['state'] = 'resolved'; self._save(db, saved)
                    continue
                members = [s for s in sources.values() if s['community_id'] == cid and s['status'] == 'matched']
                group = dict(saved) if saved else dict(id=rid, revision=0, existing_cid=cid, created_at=now())
                group.update(state='excluded' if state == 'excluded' else 'pending', name=community['community_name'],
                             district=community.get('district', ''), address=community.get('address', ''),
                             auto_review_locked=current_admission['auto_review_locked'], reason=current_admission.get('reason', ''),
                             admission_revision=current_admission['revision'])
                group['fingerprint'] = fingerprint(members, [current_admission, community['community_name'], community.get('address'), state])
                group['member_fingerprint'] = fingerprint(members)
                if not saved or saved.get('fingerprint') != group['fingerprint'] or saved.get('state') != group['state']:
                    group['revision'] += 1
                groups[rid] = group
                self._save(db, group)
                for member in members:
                    db.execute('INSERT OR REPLACE INTO review_members VALUES (?,?)', (member['id'], rid))
                    membership[member['id']] = rid
                self._save(db, group)
            # Persistent membership prevents automatic regrouping from undoing a human split/exclusion.
            for source in sources.values():
                if source['status'] != 'pending':
                    continue
                existing = groups.get(membership.get(source['id']))
                if existing and not existing.get('existing_cid') and existing['state'] in {'pending', 'excluded'}:
                    continue
                eligible = []
                for candidate in groups.values():
                    if candidate.get('existing_cid') or candidate['state'] != 'pending' or candidate.get('manual_group') or candidate.get('auto_review_locked'):
                        continue
                    members = [sources[r] for r, g in membership.items() if g == candidate['id'] and sources[r]['status'] == 'pending']
                    if members and all(same_community(source, m) for m in members):
                        eligible.append(candidate)
                group = eligible[0] if len(eligible) == 1 else dict(id='review-' + hashlib.sha256(source['id'].encode()).hexdigest()[:16],
                    state='pending', revision=0, existing_cid=None, created_at=now(), name=source['name'],
                    district=source.get('district', ''), address=source.get('address', ''), auto_review_locked=False, reason='')
                groups[group['id']] = group
                self._save(db, group)
                db.execute('INSERT OR REPLACE INTO review_members VALUES (?,?)', (source['id'], group['id']))
                membership[source['id']] = group['id']
            for group in groups.values():
                if group.get('existing_cid'):
                    if group['existing_cid'] not in masters:
                        group['state'] = 'resolved'; self._save(db, group)
                    continue
                members = [sources[r] for r, g in membership.items() if g == group['id'] and sources[r]['status'] == 'pending']
                if not members:
                    group['state'] = 'resolved'
                elif group['state'] == 'resolved':
                    group['state'] = 'pending'
                new_fingerprint = fingerprint(members)
                if group.get('fingerprint') != new_fingerprint:
                    group['revision'] += 1
                    group['fingerprint'] = new_fingerprint
                self._save(db, group)

        return views

    def reviews(self, *, state='pending', refresh=True, include_suggestions=True):
        if refresh:
            self.refresh()
        sources = {r['id']: r for r in self.store.sources()}
        facts = property_facts(self.data_dir)
        with self.store.db() as db:
            groups = self._all(db)
            membership = list(db.execute('SELECT * FROM review_members'))
        result = []
        for group in groups.values():
            if group['state'] != state:
                continue
            members = [sources[r['rid']] for r in membership if r['candidate_id'] == group['id'] and
                       (sources[r['rid']]['status'] == 'pending' or sources[r['rid']]['community_id'] == group.get('existing_cid'))]
            public_members = []
            from src.services.residential_classifier import classify_sources
            for member in members:
                m = {k: v for k, v in member.items() if k != 'samples'}
                if m['source'] == 'tmsf' and not m.get('property_type_checked_at') and not m.get('property_type'):
                    m['property_type'] = facts.get(m['source_id'], {}).get('property_type')
                m['sample_count'] = len(member.get('samples', []))
                m['residential_state'] = classify_sources([member], facts)
                public_members.append(m)
            auctions = [r for r in members if r['source'] == 'laipai']
            reasons = [group['reason']] if group.get('reason') else ['用途或小区身份需要人工确认']
            if any(m.get('auto_association_disabled') for m in members):
                reasons.append('缺少可靠小区名称或法拍身份存在冲突')
            if group.get('auto_review_locked'):
                reasons.append('人工自动审核锁已生效')
            result.append({**group, 'members': public_members, 'reasons': reasons,
                           'suggestions': [], 'sources': sorted({m['source'] for m in members}),
                           'auction_assets': len({a['source_id'] for a in auctions if a['source_kind'] == 'asset'}),
                           'auction_identity_uncertain': any(a['source_kind'] != 'asset' for a in auctions),
                           'auction_rounds': len({aid for a in auctions for aid in a.get('auction_ids', [])}),
                           'name': '小区名称缺失，需按地址核对' if members and all(m.get('community_name_missing') for m in members) else group['name']})
        result.sort(key=lambda r: (r['name'], r['id']))
        return self.add_suggestions(result) if include_suggestions else result

    def add_suggestions(self, rows):
        if not rows:
            return rows
        communities = self.store.communities()
        with self.store.db() as db:
            rejected = {}
            for r in db.execute('SELECT rid,cid FROM rejected'):
                rejected.setdefault(r['rid'], set()).add(r['cid'])
        for row in rows:
            suggested = {}
            for member in row['members']:
                for c in self.store.candidates(member, communities=communities, rejected=rejected.get(member['id'], set())):
                    if c['community_id'] != row.get('existing_cid'):
                        suggested[c['community_id']] = c
            row['suggestions'] = list(suggested.values())
        return rows

    def summary(self, *, q='', district='', source='', property_type=''):
        communities = self.refresh()
        pending = self.reviews(refresh=False, include_suggestions=False)
        with self.store.db() as db:
            excluded = sum(g['state'] == 'excluded' for g in self._all(db).values())
        sources = self.store.sources()
        members = {}
        for record in sources:
            members.setdefault(record['community_id'], []).append(record)
        residential = [c for c in communities if c['admission_state'] == 'admitted']
        return dict(residential=len(residential), pending=len(pending), excluded=excluded,
                    filtered=dict(residential=sum(community_matches(c, members.get(c['community_id'], []), q=q,
                                  district=district, source=source, property_type=property_type) for c in residential),
                                  pending=sum(review_matches(r, q=q, district=district, source=source) for r in pending)))

    def _validated(self, db, candidate_id, revision):
        row = db.execute('SELECT payload FROM review_candidates WHERE id=?', (candidate_id,)).fetchone()
        if not row:
            raise ValueError('候选不存在，请刷新')
        group = json.loads(row[0])
        if group['revision'] != revision:
            raise ValueError('候选版本已变化，请刷新重新核对')
        members = [self.store._source(r) for r in db.execute('SELECT s.* FROM sources s JOIN review_members m ON m.rid=s.id WHERE m.candidate_id=? ORDER BY s.id', (candidate_id,))]
        active = [r for r in members if r['status'] == 'pending' or (group.get('existing_cid') and r['status'] == 'matched' and r['community_id'] == group['existing_cid'])]
        if len(active) != len(members):
            raise ValueError('候选成员已关联或删除，请刷新')
        if not group.get('existing_cid') and fingerprint(active) != group.get('fingerprint'):
            raise ValueError('候选资料版本已变化，请刷新')
        if group.get('existing_cid'):
            current_ids = {r[0] for r in db.execute("SELECT id FROM sources WHERE cid=? AND status='matched'", (group['existing_cid'],))}
            if current_ids != {m['id'] for m in active} or fingerprint(active) != group.get('member_fingerprint'):
                raise ValueError('候选成员资料已变化，请刷新')
            row = db.execute('SELECT payload FROM community_admission WHERE cid=?', (group['existing_cid'],)).fetchone()
            admission = json.loads(row[0]) if row else self.store.pending_admission()
            if admission['revision'] != group['admission_revision']:
                raise ValueError('收录版本已变化，请刷新')
        return group, active

    def split(self, candidate_id, *, revision, member_ids):
        with self.store.db() as db:
            return self._split(db, candidate_id, revision=revision, member_ids=member_ids)

    def _split(self, db, candidate_id, *, revision, member_ids):
        group, members = self._validated(db, candidate_id, revision)
        if group['state'] != 'pending' or not member_ids or len(set(member_ids)) != len(member_ids) or not set(member_ids) < {m['id'] for m in members}:
            raise ValueError('请选择部分有效成员拆分，不能为空或全选')
        new = {**group, 'id': 'review-' + uuid.uuid4().hex[:16], 'existing_cid': None,
               'revision': 1, 'manual_group': True, 'auto_review_locked': True, 'reason': '人工拆分，需独立核对'}
        new.pop('admission_revision', None)
        chosen = [m for m in members if m['id'] in member_ids]
        for m in chosen:
            if group.get('existing_cid'):
                db.execute('INSERT OR IGNORE INTO rejected VALUES (?,?)', (m['id'], group['existing_cid']))
                db.execute("UPDATE sources SET cid=NULL,status='pending',method=NULL,evidence='[]' WHERE id=?", (m['id'],))
                m.update(community_id=None, status='pending', method=None, evidence=[])
        new['fingerprint'] = fingerprint(chosen)
        self._save(db, new)
        for m in chosen:
            db.execute('UPDATE review_members SET candidate_id=? WHERE rid=?', (new['id'], m['id']))
        if group.get('existing_cid'):
            admission = self.store._decide_admission(db, group['existing_cid'], 'review',
                revision=group['admission_revision'], reason='人工拆分，原小区成员需独立核对')
            group['admission_revision'] = admission['revision']
        group.update(revision=revision + 1, manual_group=True, auto_review_locked=True,
                     fingerprint=fingerprint([m for m in members if m['id'] not in member_ids]))
        self._save(db, group)
        self.store._event(db, group.get('existing_cid'), 'review_split', {'candidate_id': candidate_id, 'new_id': new['id'], 'member_ids': member_ids})
        return new

    def restore(self, candidate_id, *, revision):
        with self.store.db() as db:
            group, _ = self._validated(db, candidate_id, revision)
            if group['state'] != 'excluded':
                raise ValueError('只有已排除候选可以恢复')
            if group.get('existing_cid'):
                self.store._decide_admission(db, group['existing_cid'], 'restore-admission', revision=group['admission_revision'])
            group.update(state='pending', revision=revision + 1, auto_review_locked=True, reason='人工恢复，需重新审核')
            self._save(db, group)
            return group

    def allow_auto_review(self, candidate_id, *, revision):
        with self.store.db() as db:
            group, _ = self._validated(db, candidate_id, revision)
            if group['state'] != 'pending':
                raise ValueError('请先恢复到待审核')
            if group.get('existing_cid'):
                self.store._decide_admission(db, group['existing_cid'], 'allow-auto-review', revision=group['admission_revision'])
            group.update(auto_review_locked=False, revision=revision + 1, reason='人工允许自动审核，尚未收录')
            self._save(db, group)
            self.store._event(db, group.get('existing_cid'), 'review_allow_auto', {'candidate_id': candidate_id})
            return group

    def decide(self, candidate_id, action, *, revision, name='', property_type=None, target_id=None, reason='', member_ids=None):
        facts = property_facts(self.data_dir)
        with self.store.db() as db:
            return self._decide(db, candidate_id, action, revision=revision, name=name, property_type=property_type,
                                target_id=target_id, reason=reason, member_ids=member_ids, facts=facts)

    def _decide(self, db, candidate_id, action, *, revision, name='', property_type=None, target_id=None,
                reason='', member_ids=None, facts=None, automatic=None):
        from src.services.residential_classifier import RESIDENTIAL_TYPES, classify_sources
        if facts is None:
            facts = property_facts(self.data_dir)
        # The caller owns the same writer transaction as candidate/admission/association writes.
        group, members = self._validated(db, candidate_id, revision)
        if group['state'] != 'pending':
            raise ValueError('候选已经处理，请刷新')
        if automatic and group.get('auto_review_locked'):
            raise ValueError('人工审核锁优先')
        if member_ids is not None and set(member_ids) != {m['id'] for m in members}:
            group = self._split(db, candidate_id, revision=revision, member_ids=member_ids)
            group, members = self._validated(db, group['id'], group['revision'])
            candidate_id = group['id']
        cid = group.get('existing_cid')
        if action == 'exclude':
            if not reason.strip():
                raise ValueError('排除必须填写原因')
            if cid:
                self.store._decide_admission(db, cid, 'exclude', revision=group['admission_revision'], reason=reason)
            group.update(state='excluded', auto_review_locked=True, reason=reason.strip())
        elif action in {'admit', 'merge'}:
            if action == 'merge':
                target = db.execute('SELECT * FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (target_id,)).fetchone()
                admitted = db.execute('SELECT payload FROM community_admission WHERE cid=?', (target_id,)).fetchone()
                if not target or not admitted:
                    raise ValueError('目标必须是已收录住宅')
                admission = json.loads(admitted[0])
                target_members = [self.store._source(r) for r in db.execute("SELECT * FROM sources WHERE cid=? AND status='matched'", (target_id,))]
                if admission['state'] != 'admitted' or (admission['decision_kind'] != 'manual' and classify_sources(target_members, facts) != 'residential'):
                    raise ValueError('目标必须是有效已收录住宅')
                if cid:
                    self.store._merge(db, cid, target_id)
                cid = target_id
            else:
                if property_type not in RESIDENTIAL_TYPES or not name.strip():
                    raise ValueError('请填写小区名称并确认住宅类型')
                if not cid:
                    cid = 'local-' + uuid.uuid4().hex[:16]
                    coordinates = next((m for m in members if m.get('coordinate_system') == 'gcj02'), {})
                    payload = dict(community_id=cid, community_name=name.strip(), aliases=list(dict.fromkeys(m['name'] for m in members if m['name'] != name.strip())),
                                   district=group.get('district', ''), address=group.get('address', ''), updated_at=now(),
                                   **{k: coordinates[k] for k in ('longitude', 'latitude', 'coordinate_system') if k in coordinates})
                    db.execute('INSERT INTO communities(id,payload) VALUES (?,?)', (cid, dump(payload)))
                else:
                    row = db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()
                    payload = json.loads(row[0]); payload['community_name'] = name.strip()
                    db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), cid))
                self.store._decide_admission(db, cid, 'admit', revision=group.get('admission_revision', 1), reason=reason, property_type=property_type, automatic=automatic)
            for member in members:
                if automatic and member['status'] == 'matched' and member['community_id'] == cid:
                    continue  # Admission is separate from identity; retain its original association audit.
                self.store._associate(db, member['id'], cid, review_override=True,
                                      method='auto' if automatic else 'manual', evidence=[reason, '规则：' + automatic['rule_version']] if automatic else None)
            group.update(state='resolved', community_id=cid, auto_review_locked=False)
        else:
            raise ValueError('未知审核决定')
        group['revision'] += 1
        self._save(db, group)
        self.store._event(db, cid, 'review_' + action, {'candidate_id': candidate_id, 'member_ids': [m['id'] for m in members], 'reason': reason, **(automatic or {})})
        return group
