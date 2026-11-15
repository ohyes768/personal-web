import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  getDividendPrefix,
  normalizeSourceTab,
  readerHref,
  reportHref,
  returnHref,
  selectReport,
  sortReports,
} from './valuation-reader.ts';
import type { ValuationReportRecord } from './valuation.ts';

function makeReport(code: string, extra: Partial<ValuationReportRecord> = {}): ValuationReportRecord {
  return {
    schema_version: '1', skill_version: '1.2', code, name: `公司${code}`, currency: 'CNY',
    as_of: '2026-11-14', status: 'ready', levels: null, valuation: null, evidence: [],
    data_gaps: [], confidence: null, risks: [], invalidation_conditions: [], summary: '摘要',
    analysis: {}, report_md: '', evaluated_at: '2026-11-14T09:30:00', data_date: null,
    analysis_duration_seconds: 60, run_id: 'run-1',
    ...extra,
  };
}

describe('sortReports（阅读集合按代码升序）', () => {
  it('乱序输入按六位代码升序输出', () => {
    const reports = sortReports({
      '600004': makeReport('600004'),
      '000002': makeReport('000002'),
      '000100': makeReport('000100'),
    });
    assert.deepEqual(reports.map(r => r.code), ['000002', '000100', '600004']);
  });

  it('空集合返回空数组', () => {
    assert.deepEqual(sortReports({}), []);
    assert.deepEqual(sortReports(null), []);
  });
});

describe('selectReport（选当前公司）', () => {
  const reports = [makeReport('000002'), makeReport('600004')];

  it('code 为 null 时落到第一篇', () => {
    assert.equal(selectReport(reports, null)?.code, '000002');
  });

  it('code 命中时取该篇', () => {
    assert.equal(selectReport(reports, '600004')?.code, '600004');
  });

  it('code 找不到时返回 null（不静默换成别家）', () => {
    assert.equal(selectReport(reports, '999999'), null);
  });

  it('空集合返回 null', () => {
    assert.equal(selectReport([], '600004'), null);
  });
});

describe('readerHref / reportHref（主页面 → 阅读页）', () => {
  it('默认不带 code，阅读页自己落到第一篇', () => {
    assert.equal(readerHref('/', new URLSearchParams()), '/valuation-reader');
  });

  it('带上来源 tab', () => {
    assert.equal(readerHref('/', new URLSearchParams('tab=alerts')), '/valuation-reader?fromTab=alerts');
    assert.equal(readerHref('/', new URLSearchParams('tab=screening')), '/valuation-reader?fromTab=screening');
  });

  it('线上带 /dividend 前缀', () => {
    assert.equal(
      readerHref('/dividend/', new URLSearchParams('tab=alerts')),
      '/dividend/valuation-reader?fromTab=alerts',
    );
  });

  it('reportHref 指定股票代码', () => {
    assert.equal(
      reportHref('/dividend/', '600004', new URLSearchParams('tab=alerts')),
      '/dividend/valuation-reader?code=600004&fromTab=alerts',
    );
    assert.equal(
      reportHref('/', '600004', new URLSearchParams()),
      '/valuation-reader?code=600004',
    );
  });

  it('忽略任意 returnUrl，不透传', () => {
    assert.equal(
      readerHref('/', new URLSearchParams('tab=alerts&returnUrl=https://evil.example/x')),
      '/valuation-reader?fromTab=alerts',
    );
  });
});

describe('returnHref（阅读页 → 主页面）', () => {
  it('回到进入前的视图', () => {
    assert.equal(returnHref('/valuation-reader', new URLSearchParams('fromTab=alerts')), '/?tab=alerts');
    assert.equal(returnHref('/dividend/valuation-reader', new URLSearchParams('fromTab=alerts')), '/dividend/?tab=alerts');
  });

  it('all + 只看收藏能还原', () => {
    assert.equal(returnHref('/valuation-reader', new URLSearchParams('fromTab=all&fromFav=1')), '/?fav=1');
  });

  it('非法 tab 归到主页面首页', () => {
    assert.equal(returnHref('/valuation-reader', new URLSearchParams('fromTab=bogus')), '/');
  });
});

describe('线上前缀与 tab 归一化', () => {
  it('只有 /dividend 开头才算线上', () => {
    assert.equal(getDividendPrefix('/dividend/valuation-reader'), '/dividend');
    assert.equal(getDividendPrefix('/valuation-reader'), '');
    assert.equal(getDividendPrefix('/dividend-other/x'), '');
  });

  it('旧 watchlist 等价于 全部 + 只看收藏', () => {
    assert.equal(normalizeSourceTab('watchlist'), 'all');
    assert.equal(normalizeSourceTab('alerts'), 'alerts');
    assert.equal(normalizeSourceTab(null), 'all');
  });
});
