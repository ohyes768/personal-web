"""Explainable local-only review. Preview projects into memory; execution is opt-in."""
from src.services.community_address import effective_address

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from src.core.boundary import is_in_scope, is_in_xiaoshan_border
from src.services.community_admission import effective_type, property_facts
from src.services.community_registry import CommunityRegistry, dump, normalized, now
from src.services.community_review import ReviewWorkspace, same_community
from src.services.residential_classifier import classify_sources

RULE_VERSION = 'community-auto-v2'
TABLES = ('communities', 'sources', 'community_admission', 'rejected', 'review_candidates', 'review_members')
SUSPICIOUS_NAME = re.compile(r'(?:大道|路|街|巷)(?:小区)?$|(?:停车场|车库|售楼处|出入口|门岗|物业服务中心)$')


def rows(db, table):
    return sorted([dict(r) for r in db.execute('SELECT * FROM ' + table)], key=lambda r: dump(r))


def snapshot_id(db, facts):
    return hashlib.sha256(dump([RULE_VERSION, {t: rows(db, t) for t in TABLES}, facts]).encode()).hexdigest()


class MemoryRegistry(CommunityRegistry):
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def db(self):
        yield self.connection


def identity(master):
    return {**master, 'name': master['community_name']}


def evidence(record, facts):
    fields = ('id', 'source', 'source_id', 'name', 'district', 'address', 'property_type', 'property_type_error',
              'property_type_checked_at', 'property_type_url', 'samples', 'source_url')
    value = {k: record.get(k) for k in fields}
    if record['source'] == 'tmsf' and not record.get('property_type_checked_at') and not record.get('property_type'):
        legacy = facts.get(record['source_id'], {})
        value.update(property_type=legacy.get('property_type'), legacy_property_fact=legacy)
    return value


def decide(group, members, *, groups, sources, masters, admissions, rejected, facts):
    """Pure conservative rule matrix, no registry calls, writes or upstream requests."""
    item = dict(candidate_id=group['id'], revision=group['revision'], member_ids=sorted(m['id'] for m in members),
                name=group['name'], action='pending', reasons=[], evidence=[evidence(m, facts) for m in members])
    def result(action, reason, **extra):
        return {**item, 'action': action, 'reasons': [reason], **extra}
    cid = group.get('existing_cid')
    if group['state'] == 'excluded':
        return result('protected', '保留已有排除决定，自动流程不恢复')
    if group['state'] != 'pending' or group.get('auto_review_locked') or (cid and admissions.get(cid, {}).get('auto_review_locked')):
        return result('pending', '人工锁或已有排除决定优先')
    if not members or any(m.get('auto_association_disabled') or m.get('community_name_missing') for m in members):
        return result('pending', '小区名称或身份不可靠')
    if not effective_address(group.get('address'), members):
        return result('exclude', '缺少有效地址，不收录')
    if SUSPICIOUS_NAME.search(group['name']):
        return result('pending', '名称疑似道路或附属设施，须人工核对')
    district = normalized(group.get('district')).removesuffix('区')
    address = effective_address(group.get('address'), members)
    if district not in {'滨江', '萧山'}:
        return result('exclude', '区域不在住宅目录范围；建议人工排除')
    if not address or district + '区' not in address:
        return result('pending', '缺少同区域的可靠地址证据')
    positioned = [m for m in members if m.get('longitude') is not None or m.get('latitude') is not None]
    for m in positioned:
        lng, lat = m.get('longitude'), m.get('latitude')
        if m.get('coordinate_system') != 'gcj02' or not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in (lng, lat)):
            return result('pending', '坐标缺失或坐标系不可靠')
        if not is_in_scope(lng, lat) or (district == '萧山' and not is_in_xiaoshan_border(lng, lat)):
            return result('exclude', '坐标在目录范围外；建议人工排除')
    if district == '萧山' and not positioned:
        return result('pending', '萧山接壤范围需要坐标核实')
    if not all(same_community(a, b) for a in members for b in members if a['id'] != b['id']):
        return result('pending', '成员的小区身份或分期存在冲突')
    if cid:
        master = next((m for m in masters if m['community_id'] == cid and not m.get('deleted') and not m.get('merged_to')), None)
        if not master:
            return result('pending', '原主档已删除或合并')
        names = {normalized(n) for n in [master['community_name'], master.get('community_alias'), *master.get('aliases', [])] if n}
        if not all(normalized(m['name']) in names and same_community({**m, 'name': master['community_name']}, identity(master)) for m in members):
            return result('pending', '主档与来源的名称或地址身份存在疑点')
    # Same identity, not a global name blacklist: changed external IDs still honor vetoes.
    if any(same_community(a, b) for a in members for b in sources if b['status'] == 'ignored'):
        return result('pending', '同一来源身份有人工忽略记录')
    for other in groups:
        if other['id'] == group['id']:
            continue
        other_members = [m for m in sources if m['id'] in other.get('member_ids', [])]
        if (other.get('auto_review_locked') or other['state'] == 'excluded') and any(same_community(a, b) for a in members for b in other_members):
            return result('pending', '同一身份已有人工决定，外部编号变化不能覆盖')
    hits = []
    for master in masters:
        if master['community_id'] == cid:
            continue
        names = {normalized(n) for n in [master['community_name'], master.get('community_alias'), *master.get('aliases', [])] if n}
        suspicious = any(normalized(m['name']) in n or n in normalized(m['name']) for m in members for n in names)
        if not suspicious:
            continue
        if master.get('deleted') or master.get('merged_to') or admissions.get(master['community_id'], {}).get('auto_review_locked') or admissions.get(master['community_id'], {}).get('state') == 'excluded':
            if any(same_community({**m, 'name': master['community_name']}, identity(master)) for m in members if normalized(m['name']) in names):
                return result('pending', '同一身份已删除、排除或被人工锁定')
            continue
        hits.append(master)
    if hits:
        if len(hits) != 1:
            return result('pending', '多个已有小区身份疑点')
        target = hits[0]; target_id = target['community_id']
        exact = all(normalized(m['name']) in {normalized(n) for n in [target['community_name'], target.get('community_alias'), *target.get('aliases', [])] if n} and
                    same_community({**m, 'name': target['community_name']}, identity(target)) for m in members)
        target_admission = admissions.get(target_id, {})
        target_members = [m for m in sources if m['community_id'] == target_id and m['status'] == 'matched']
        admitted = target_admission.get('state') == 'admitted' and (target_admission.get('decision_kind') == 'manual' or classify_sources(target_members, facts) == 'residential')
        if exact and admitted and not cid and not any((m['id'], target_id) in rejected for m in members):
            has_use_evidence = any(m['source'] in {'tmsf', 'fang'} for m in members)
            if has_use_evidence and classify_sources([*target_members, *members], facts) != 'residential':
                return result('pending', '补充来源会造成用途冲突')
            if sum(m['source'] == 'fang' for m in [*target_members, *members]) > 1:
                return result('pending', '房天下来源唯一性冲突')
            return result('merge', '完整名称/别名、区域与地址或位置一致，补充已有住宅来源', target_id=target_id)
        return result('pending', '已有同名、分期或相似小区，须人工核对')
    for other in groups:
        if other['id'] != group['id'] and other['state'] == 'pending' and (normalized(group['name']) in normalized(other['name']) or normalized(other['name']) in normalized(group['name'])):
            return result('pending', '另有同名候选，地址或分期仍有疑点')
    if any(rid in {m['id'] for m in members} for rid, _ in rejected):
        return result('pending', '来源有人工拒绝关联记录')
    classification = classify_sources(members, facts)
    if classification == 'non_residential':
        return result('exclude', '明确非住宅用途；建议人工排除')
    if classification != 'residential':
        return result('pending', '缺少充分住宅证据，或最新用途失败/混合/冲突')
    if sum(m['source'] == 'fang' for m in members) > 1:
        return result('pending', '房天下来源唯一性冲突')
    return result('admit', '住宅用途明确、名称区域地址可靠，未发现重复身份疑点', property_type=effective_type(members, facts))


class AutoReview:
    def __init__(self, store, data_dir):
        self.store, self.data_dir = store, Path(data_dir)

    def _preview(self):
        facts = property_facts(self.data_dir)
        with sqlite3.connect(self.store.path.as_uri() + '?mode=ro', uri=True) as original, sqlite3.connect(':memory:') as memory:
            original.row_factory = memory.row_factory = sqlite3.Row
            original.execute('BEGIN')
            sid = snapshot_id(original, facts)
            original.backup(memory)
            clone = MemoryRegistry(memory)
            work = ReviewWorkspace(clone, self.data_dir)
            work.refresh()
            groups = list(work._all(memory).values())
            membership = rows(memory, 'review_members')
            for g in groups:
                g['member_ids'] = [m['rid'] for m in membership if m['candidate_id'] == g['id']]
            sources = clone.sources()
            masters = [clone._community(r) for r in memory.execute('SELECT * FROM communities ORDER BY id')]
            admissions = {r['cid']: json.loads(r['payload']) for r in memory.execute('SELECT * FROM community_admission')}
            rejected = {(r['rid'], r['cid']) for r in memory.execute('SELECT * FROM rejected')}
            items = [decide(g, [m for m in sources if m['id'] in g['member_ids']], groups=groups, sources=sources,
                            masters=masters, admissions=admissions, rejected=rejected, facts=facts)
                     for g in sorted(groups, key=lambda g: g['id']) if g['state'] in {'pending', 'excluded'}]
            report = dict(snapshot_id=sid, rule_version=RULE_VERSION, items=items,
                          counts={a: sum(i['action'] == a for i in items) for a in ('admit', 'merge', 'pending', 'exclude', 'protected')})
            projection = {t: rows(memory, t) for t in ('review_candidates', 'review_members')}
            if facts != property_facts(self.data_dir):
                raise ValueError('用途资料已变化，请重新预演')
            return report, projection, facts

    def preview(self):
        return self._preview()[0]

    def status(self):
        with self.store.db() as db:
            saved = {r['key']: json.loads(r['value']) for r in db.execute("SELECT * FROM meta WHERE key IN ('auto_review_enabled','auto_review_report','auto_review_rule_version')")}
        return dict(enabled=saved.get('auto_review_enabled', False) is True and saved.get('auto_review_rule_version') == RULE_VERSION,
                    rule_version=RULE_VERSION, last_report=saved.get('auto_review_report'))

    def configure(self, enabled, reviewed_snapshot=None):
        if enabled and self.preview()['snapshot_id'] != reviewed_snapshot:
            raise ValueError('请先预演并核对最新结果，资料已变化时需要重新预演')
        with self.store.db() as db:
            if enabled and snapshot_id(db, property_facts(self.data_dir)) != reviewed_snapshot:
                raise ValueError('资料已变化，请重新预演')
            db.execute("INSERT OR REPLACE INTO meta VALUES ('auto_review_enabled',?)", (dump(bool(enabled)),))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('auto_review_rule_version',?)", (dump(RULE_VERSION),))
            self.store._event(db, None, 'auto_review_configure', {'enabled': bool(enabled), 'rule_version': RULE_VERSION})
        return self.status()

    def execute(self, reviewed_snapshot):
        report, projection, facts = self._preview()
        if report['snapshot_id'] != reviewed_snapshot:
            raise ValueError('资料已变化，请重新预演')
        results = []
        with self.store.db() as db:
            setting = db.execute("SELECT value FROM meta WHERE key='auto_review_enabled'").fetchone()
            version = db.execute("SELECT value FROM meta WHERE key='auto_review_rule_version'").fetchone()
            if not setting or json.loads(setting[0]) is not True or not version or json.loads(version[0]) != RULE_VERSION:
                raise ValueError('自动审核尚未启用，请先核对预演结果')
            if snapshot_id(db, property_facts(self.data_dir)) != reviewed_snapshot:
                raise ValueError('资料已变化，请重新预演')
            for r in projection['review_candidates']:
                db.execute('INSERT OR REPLACE INTO review_candidates VALUES (?,?)', (r['id'], r['payload']))
            for r in projection['review_members']:
                db.execute('INSERT OR REPLACE INTO review_members VALUES (?,?)', (r['rid'], r['candidate_id']))
            work = ReviewWorkspace(self.store, self.data_dir)
            for item in report['items']:
                if item['action'] not in {'admit', 'merge'}:
                    results.append({**item, 'outcome': 'skipped'}); continue
                db.execute('SAVEPOINT auto_candidate')
                try:
                    decision = work._decide(db, item['candidate_id'], item['action'], revision=item['revision'],
                        name=item['name'], property_type=item.get('property_type'), target_id=item.get('target_id'),
                        reason='；'.join(item['reasons']), facts=facts,
                        automatic=dict(rule_version=RULE_VERSION, evidence=item['evidence'], batch_id=reviewed_snapshot, decided_at=now()))
                    results.append({**item, 'outcome': 'applied', 'community_id': decision.get('community_id')})
                except ValueError as exc:
                    db.execute('ROLLBACK TO auto_candidate')
                    results.append({**item, 'outcome': 'conflict', 'error': str(exc)})
                finally:
                    db.execute('RELEASE auto_candidate')
            report = {**report, 'items': results, 'executed_at': now(), 'counts': dict(Counter(i['outcome'] for i in results))}
            db.execute("INSERT OR REPLACE INTO meta VALUES ('auto_review_report',?)", (dump(report),))
            self.store._event(db, None, 'auto_review_batch', report)
        return report

    def after_collection(self):
        preview = self.preview()
        return self.execute(preview['snapshot_id']) if self.status()['enabled'] else preview


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Local read-only community auto-review preview')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--report', action='store_true', help='Export into diagnostics/auto-review; no business writes')
    args = parser.parse_args()
    root = Path(args.data_dir).resolve()
    registry = CommunityRegistry.__new__(CommunityRegistry)
    registry.path = root / 'community_registry.sqlite3'
    if not registry.path.exists():
        parser.error('Existing community registry required')
    report = AutoReview(registry, root).preview()
    if args.report:
        target = root / 'diagnostics' / 'auto-review'
        target.mkdir(parents=True, exist_ok=True)
        (target / (report['snapshot_id'] + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'snapshot_id': report['snapshot_id'], 'rule_version': report['rule_version'], 'counts': report['counts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
