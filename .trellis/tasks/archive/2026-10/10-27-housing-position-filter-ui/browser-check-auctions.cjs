/* eslint-disable */
// 法拍待关联页签的筛选栏布局核查：法拍保留自己的搜索/跳过/同步，不套入住宅目录筛选。
const { chromium } = require('F:/personal-projects/personal-web/apps/dividend/node_modules/playwright');
const BASE = process.env.HOUSING_QA_URL || 'http://localhost:3017';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const requests = [];
  await page.route('**/api/map/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/map/, '');
    requests.push({ path, query: url.search });
    if (path.endsWith('/summary')) return route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { active: true, pipeline: true, admitted: 89, pending: 12, excluded: 40, auction_pending: 3 } }) });
    if (path.endsWith('/auctions')) return route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { items: [], total: 0, page: 1 } }) });
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: null }) });
  });
  await page.goto(`${BASE}/map`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: '小区数据管理' }).click();
  await page.waitForSelector('.directory-toolbar', { timeout: 20000 });
  await page.getByRole('button', { name: /^法拍待关联/ }).click();
  await page.waitForTimeout(700);
  console.log(JSON.stringify({
    labels: await page.$$eval('.directory-filter-field > span', n => n.map(x => x.textContent)),
    moreExists: await page.$('.directory-filter-more') !== null,
    chips: await page.$$eval('.directory-filter-chip', n => n.map(x => x.textContent.trim())),
    hasSkipToggle: await page.$('.directory-toolbar input[type=checkbox]') !== null,
    hasSyncButton: await page.getByRole('button', { name: /同步历史法拍/ }).count() > 0,
    auctionQuery: requests.filter(r => r.path.endsWith('/auctions')).map(r => r.query),
    catalogQueries: requests.filter(r => r.path.endsWith('/catalog')).map(r => r.query),
  }, null, 2));
  await browser.close();
})().catch(e => { console.error('FAILED', e); process.exit(1); });
