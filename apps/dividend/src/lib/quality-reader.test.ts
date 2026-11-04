import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  getDividendPrefix,
  normalizeSourceTab,
  readerHref,
  returnHref,
  selectReport,
  sortReports,
} from './quality-reader.ts';
import type { QualityScore } from './quality.ts';

function makeScore(code: string, extra: Partial<QualityScore> = {}): QualityScore {
  return {
    code,
    name: `公司${code}`,
    dimensions: { business: 4, moat: 3, industry: null, management: 4, financial: null },
    weighted_score: null,
    stars: null,
    boundary: null,
    summary: '摘要',
    risks: [],
    watch_points: [],
    report_md: '正文',
    scored_at: '2026-11-01 10:00',
    data_date: '2026-10-30',
    ...extra,
  };
}

describe('sortReports（阅读集合按代码升序）', () => {
  it('乱序输入按六位代码升序输出', () => {
    const reports = sortReports({
      '000009': makeScore('000009'),
      '000002': makeScore('000002'),
      '000100': makeScore('000100'),
    });
    assert.deepEqual(reports.map(r => r.code), ['000002', '000009', '000100']);
  });

  it('存在 null 维度的未评级报告同样进入集合', () => {
    const reports = sortReports({ '000002': makeScore('000002') });
    assert.equal(reports.length, 1);
    assert.equal(reports[0].dimensions.financial, null);
  });

  it('空集合返回空数组', () => {
    assert.deepEqual(sortReports({}), []);
  });
});

describe('selectReport（当前公司选择）', () => {
  const reports = [makeScore('000001'), makeScore('000002')];

  it('没有 code 时默认第一篇', () => {
    assert.equal(selectReport(reports, null)?.code, '000001');
  });

  it('code 命中时返回对应报告', () => {
    assert.equal(selectReport(reports, '000002')?.code, '000002');
  });

  it('未知或非法 code 返回 null（不静默换成别家）', () => {
    assert.equal(selectReport(reports, '999999'), null);
    assert.equal(selectReport(reports, ''), null);
    assert.equal(selectReport(reports, 'abc'), null);
  });

  it('空集合没有当前项', () => {
    assert.equal(selectReport([], null), null);
  });
});

describe('getDividendPrefix（线上前缀边界）', () => {
  it('只有 /dividend 或 /dividend/ 开头算线上', () => {
    assert.equal(getDividendPrefix('/dividend'), '/dividend');
    assert.equal(getDividendPrefix('/dividend/'), '/dividend');
    assert.equal(getDividendPrefix('/dividend/quality-reader'), '/dividend');
  });

  it('本地根路径与其他同名前缀不算线上', () => {
    assert.equal(getDividendPrefix('/'), '');
    assert.equal(getDividendPrefix('/quality-reader'), '');
    assert.equal(getDividendPrefix('/dividend-other/'), '');
    assert.equal(getDividendPrefix('/dividends'), '');
  });
});

describe('normalizeSourceTab', () => {
  it('只接受 all/alerts/screening，其余归一为 all', () => {
    assert.equal(normalizeSourceTab('alerts'), 'alerts');
    assert.equal(normalizeSourceTab('screening'), 'screening');
    assert.equal(normalizeSourceTab('all'), 'all');
    assert.equal(normalizeSourceTab('watchlist'), 'all');
    assert.equal(normalizeSourceTab(null), 'all');
    assert.equal(normalizeSourceTab('https://evil.example'), 'all');
  });
});

describe('readerHref（主页面 → 阅读页）', () => {
  it('本地路径不带线上前缀', () => {
    assert.equal(readerHref('/', new URLSearchParams()), '/quality-reader');
    assert.equal(readerHref('/', new URLSearchParams('tab=screening')), '/quality-reader?fromTab=screening');
  });

  it('线上路径保留 /dividend 前缀', () => {
    assert.equal(readerHref('/dividend/', new URLSearchParams('tab=screening')), '/dividend/quality-reader?fromTab=screening');
  });

  it('旧 watchlist 归一成 all + 收藏', () => {
    assert.equal(readerHref('/', new URLSearchParams('tab=watchlist')), '/quality-reader?fromTab=all&fromFav=1');
  });

  it('只在全部视图保留 fav', () => {
    assert.equal(readerHref('/', new URLSearchParams('fav=1')), '/quality-reader?fromTab=all&fromFav=1');
    assert.equal(readerHref('/', new URLSearchParams('tab=alerts&fav=1')), '/quality-reader?fromTab=alerts');
  });

  it('忽略任意 returnUrl，不允许外部地址', () => {
    assert.equal(readerHref('/', new URLSearchParams('returnUrl=https://evil.example/x')), '/quality-reader');
  });
});

describe('returnHref（阅读页 → 主页面）', () => {
  it('默认回首页', () => {
    assert.equal(returnHref('/quality-reader', new URLSearchParams()), '/');
    assert.equal(returnHref('/dividend/quality-reader', new URLSearchParams()), '/dividend/');
  });

  it('按 fromTab 回到原视图', () => {
    assert.equal(returnHref('/quality-reader', new URLSearchParams('fromTab=screening')), '/?tab=screening');
    assert.equal(returnHref('/dividend/quality-reader', new URLSearchParams('fromTab=screening')), '/dividend/?tab=screening');
    assert.equal(returnHref('/dividend/quality-reader', new URLSearchParams('fromTab=alerts')), '/dividend/?tab=alerts');
  });

  it('全部视图的收藏过滤可回跳', () => {
    assert.equal(returnHref('/quality-reader', new URLSearchParams('fromTab=all&fromFav=1')), '/?fav=1');
  });

  it('非法 fromTab 归一回首页；fav 只在 all 生效', () => {
    assert.equal(returnHref('/quality-reader', new URLSearchParams('fromTab=bogus')), '/');
    assert.equal(returnHref('/quality-reader', new URLSearchParams('fromTab=screening&fromFav=1')), '/?tab=screening');
  });
});
