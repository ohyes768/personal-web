/* eslint-disable */
// 一次性浏览器验收脚本：拦截 /api/map 请求喂假数据，不碰真实后端与生产数据。
// Playwright 只装在 apps/dividend/node_modules，按该路径 require。
const { chromium } = require('F:/personal-projects/personal-web/apps/dividend/node_modules/playwright');

const BASE = process.env.HOUSING_QA_URL || 'http://localhost:3017';
const OUT = process.env.HOUSING_QA_OUT || 'F:/personal-projects/personal-web/.playwright-cli';

const candidates = [
  { source_id: 'B1', name: '鸿雁苑', address: '', longitude: 120.202578, latitude: 30.165324,
    poi_type: '房地产;住宅小区;普通住宅', poi_typecode: '120302', name_matched: true },
  { source_id: 'B2', name: '鸿雁苑南门商业街', address: '江南大道 100 号', longitude: 120.201, latitude: 30.164,
    poi_type: '公司企业;公司;公司', poi_typecode: '050000', name_matched: true },
];
const references = [
  { source_id: 'R1', name: '滨和路公交站', address: '滨和路口', poi_type: '交通设施;公交车站', poi_typecode: '150900' },
];

const catalogRow = {
  community_id: 'c1', community_name: '鸿雁苑', district: '滨江', address: '江南大道与江晖路交叉口',
  market_state: 'new_house', property_types: ['住宅'], effective_property_type: '住宅',
  admission_state: 'admitted', workflow_state: 'admitted', qualification: '', facts_state: 'complete',
  exclusion_reason: '', sources: [], aliases: [],
  coverage: { auction: { round_count: 0, property_count: 0, unidentified_round_count: 0 },
    rental: { state: 'pending', sample_count: 0 } },
};

const requests = [];

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  await page.route('**/api/map/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/map/, '');
    const method = route.request().method();
    if (method === 'POST') {
      const body = route.request().postData();
      requests.push({ path, method, body });
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { state: 'manual', has_coordinates: true, revision: 'rev-2',
          candidates: [], selected: { source_id: 'B1', name: '鸿雁苑', address: '', longitude: 120.202578,
            latitude: 30.165324 }, coordinates_verified: true } }) });
      return;
    }
    requests.push({ path, method, query: url.search });
    if (path.endsWith('/summary')) {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { active: true, pipeline: true, admitted: 89, pending: 12, excluded: 40, auction_pending: 3 } }) });
      return;
    }
    if (/\/catalog\/[^/]+\/position$/.test(path)) {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { state: 'review', has_coordinates: true, revision: 'rev-1',
          candidates, reference_candidates: references } }) });
      return;
    }
    if (/\/catalog\/[^/]+$/.test(path)) {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ success: true, data: catalogRow }) });
      return;
    }
    if (path.endsWith('/catalog')) {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { items: [catalogRow], total: 1, page: 1, property_types: ['住宅'] } }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: null }) });
  });

  await page.goto(`${BASE}/map`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: '小区数据管理' }).click();
  await page.waitForSelector('.directory-toolbar', { timeout: 20000 });

  const report = {};

  // —— 筛选栏结构 ——
  report.filterLabels = await page.$$eval('.directory-filter-field > span', nodes => nodes.map(n => n.textContent));
  report.moreSummary = await page.$eval('.directory-filter-more > summary', n => n.textContent);
  report.summaryChips = await page.$$eval('.directory-filter-chip', nodes => nodes.map(n => n.textContent.trim()));
  report.count = await page.$eval('.directory-filter-count', n => n.textContent);

  // —— 请求参数：只有适用条件 ——
  await page.selectOption('.directory-filter-field:has(span:text("房源类型")) select', 'new_house');
  await page.waitForTimeout(600);
  report.catalogQuery = requests.filter(r => r.path.endsWith('/catalog')).map(r => r.query);

  // —— 更多筛选折叠 ——
  await page.click('.directory-filter-more > summary');
  await page.waitForTimeout(200);
  report.moreVisible = await page.$$eval('.directory-filter-more-fields .directory-filter-field > span', nodes => nodes.map(n => n.textContent));
  report.moreCountAfter = await page.$eval('.directory-filter-more > summary', n => n.textContent);

  // —— 切页签：搜索和区域保留，页签专属条件清掉 ——
  await page.selectOption('.directory-filter-field:has(span:text("房源类型")) select', '');
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: /^不收录/ }).click();
  await page.waitForTimeout(600);
  report.excludedLabels = await page.$$eval('.directory-filter-field > span', nodes => nodes.map(n => n.textContent));
  report.excludedQuery = requests.filter(r => r.path.endsWith('/catalog')).map(r => r.query).pop();

  await page.click('.directory-filter-more > summary');
  await page.waitForTimeout(200);
  await page.screenshot({ path: `${OUT}/qa-filters-1440.png`, fullPage: true });
  await page.click('.directory-filter-more > summary');
  await page.waitForTimeout(200);

  // —— 地点确认：候选卡片 + 地图链接 + 禁用原因 ——
  await page.getByRole('button', { name: /^已收录/ }).click();
  await page.waitForTimeout(600);
  await page.getByRole('button', { name: '查看资料' }).click();
  await page.waitForSelector('.directory-candidate-list', { timeout: 15000 });

  report.statusLine = await page.$eval('.directory-position-status', n => n.textContent);
  report.candidateCards = await page.$$eval('.directory-candidate-card', nodes => nodes.map(n => ({
    name: n.querySelector('.directory-candidate-name')?.textContent,
    lines: [...n.querySelectorAll('.directory-candidate-lines span')].map(s => s.textContent),
    selected: n.getAttribute('data-selected'),
  })));
  report.confirmBlocker = await page.$eval('.directory-position-blocker', n => n.textContent).catch(() => null);
  report.markerLink = await page.$eval('.directory-position-review a', n => n.href).catch(() => null);
  await page.screenshot({ path: `${OUT}/qa-position-review-1440.png`, fullPage: true });

  // 选候选 B2（有地址）→ 确认按钮应可用
  await page.click('.directory-candidate-card:nth-child(3) input[type=radio]');
  await page.waitForTimeout(200);
  report.afterPickBlocker = await page.$eval('.directory-position-blocker', n => n.textContent).catch(() => null);
  report.afterPickStatus = await page.$eval('.directory-position-status', n => n.textContent);

  // 回到 B1（无地址）→ 需要勾选核对
  await page.click('.directory-candidate-card:nth-child(2) input[type=radio]');
  await page.waitForTimeout(200);
  report.needsCheckbox = await page.$('.directory-position-verify input[type=checkbox]') !== null;
  report.b1Blocker = await page.$eval('.directory-position-blocker', n => n.textContent).catch(() => null);

  await page.check('.directory-position-verify input[type=checkbox]');
  await page.waitForTimeout(200);
  report.b1VerifiedBlocker = await page.$eval('.directory-position-blocker', n => n.textContent).catch(() => null);
  report.b1VerifiedCheckbox = await page.$eval('.directory-position-verify input[type=checkbox]', n => n.checked);

  // 提交确认 → 检查 payload
  await page.click('.directory-position-confirm .btn-primary');
  await page.waitForTimeout(600);
  report.confirmPost = requests.filter(r => r.method === 'POST' && r.path.includes('/position/confirm')).map(r => r.body);

  await page.screenshot({ path: `${OUT}/qa-position-1440.png`, fullPage: true });

  // —— 390px 手机端 ——
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  report.mobileOverflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
  }));
  report.mobileSearchWidth = await page.$eval('.directory-filter-search', n => Math.round(n.getBoundingClientRect().width));
  report.mobileFieldWidths = await page.$$eval('.directory-filter-field', nodes =>
    nodes.map(n => Math.round(n.getBoundingClientRect().width)));
  await page.screenshot({ path: `${OUT}/qa-filters-390.png`, fullPage: true });
  // 候选卡片在 390px 下的排布：确认后详情已变为已确认，重新加载再打开待确认详情。
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: '小区数据管理' }).click();
  await page.waitForSelector('.directory-toolbar', { timeout: 20000 });
  await page.getByRole('button', { name: '查看资料' }).click();
  await page.waitForSelector('.directory-candidate-list', { timeout: 15000 });
  await page.waitForTimeout(400);
  report.mobileCandidateOverflow = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.directory-candidate-card')];
    return {
      count: cards.length,
      overflowing: cards.filter(c => c.scrollWidth > c.clientWidth + 1).length,
      dialogOverflow: (() => {
        const d = document.querySelector('dialog');
        return d ? d.scrollWidth > d.clientWidth + 1 : null;
      })(),
      confirmStacked: (() => {
        const c = document.querySelector('.directory-position-confirm');
        if (!c) return null;
        const btn = c.querySelector('.btn');
        return btn ? Math.round(btn.getBoundingClientRect().width) : null;
      })(),
    };
  });
  await page.screenshot({ path: `${OUT}/qa-position-390.png`, fullPage: true });

  console.log(JSON.stringify(report, null, 2));
  await browser.close();
}

main().catch(e => { console.error('FAILED', e); process.exit(1); });
