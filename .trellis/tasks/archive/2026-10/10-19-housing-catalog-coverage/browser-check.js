async page => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  const states = ['data', 'pending', 'unmapped', 'source_missing', 'no_samples', 'failed'];
  const rows = Array.from({ length: 35 }, (_, i) => ({
    community_id: String(i), community_name: i === 0 ? '示例·滨江钱塘世纪花园（东区）' : `示例花园${String(i).padStart(2, '0')}`,
    district: '滨江', address: '江南大道与月明路交叉口附近的较长示例地址', aliases: [], admission_state: 'admitted',
    market_state: 'second_hand', qualification: 'eligible', facts_state: 'complete', sources: [],
    position: { state: 'matched', bucket: 'done', has_coordinates: true, map_status: 'displayed', candidates: [] },
    coverage: { auction: { property_count: i % 3 === 0 ? 2 : 0, round_count: i % 3 === 0 ? 4 : 0, unidentified_round_count: i % 3 === 0 ? 1 : 0 },
      rental: { state: states[i % 6], sample_count: i % 6 === 0 ? 12 : 0, captured_at: i % 6 === 0 ? '2026-08-01T00:00:00Z' : null,
        stale: i % 6 === 0, update_failed: i % 6 === 0, error: i % 6 === 0 ? '示例更新失败，保留旧数据' : null } }
  }));
  const requests = [];
  await page.route('**/api/map/**', async route => {
    const [path, query = ''] = route.request().url().split('/api/map')[1].split('?');
    const params = Object.fromEntries(query.split('&').filter(Boolean).map(pair => pair.split('=').map(decodeURIComponent)));
    const url = { searchParams: { get: key => params[key] || null } };
    let data = null;
    if (path === '/directory/workflow/summary') data = { active: true, admitted: rows.length, excluded: 0, auction_pending: 0 };
    else if (path === '/directory/workflow/catalog') {
      requests.push(params);
      let selected = rows.filter(r => !url.searchParams.get('q') || r.community_name.includes(url.searchParams.get('q')));
      const auction = url.searchParams.get('auction'), rental = url.searchParams.get('rental');
      if (auction) selected = selected.filter(r => Boolean(r.coverage.auction.round_count) === (auction === 'has'));
      if (rental) selected = selected.filter(r => r.coverage.rental.state === rental);
      if (url.searchParams.get('state') === 'excluded') selected = [];
      const n = Number(url.searchParams.get('page') || 1);
      data = { items: selected.slice((n - 1) * 30, n * 30), total: selected.length, page: n };
    } else if (/\/catalog\/[^/]+\/position$/.test(path)) data = { state: 'matched', candidates: [], has_coordinates: true, map_status: 'displayed' };
    else if (/\/catalog\/[^/]+$/.test(path)) {
      data = { ...rows.find(r => r.community_id === path.split('/').pop()), auction_records: [
        { source: 'laipai', auction_id: 'a', asset_id: 'x', title: '示例房产一拍', round: 1, status: 'failure' },
        { source: 'laipai', auction_id: 'b', asset_id: 'x', title: '示例房产二拍', round: 2, status: 'done' }
      ] };
    } else if (path === '/communities') data = [];
    else if (path === '/auctions/community-summary') data = { available: false, counts: {} };
    else if (path === '/market-reference') data = { available: false };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data }) });
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto('http://localhost:3007/map', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')].find(b => b.textContent === '小区数据管理');
    return button && Object.keys(button).some(k => k.startsWith('__reactProps$') && typeof button[k]?.onClick === 'function');
  });
  await page.getByRole('button', { name: '小区数据管理', exact: true }).click();
  await page.getByRole('button', { name: '下一页', exact: true }).waitFor();
  await page.locator('.catalog-data-link').first().waitFor();
  await page.screenshot({ path: '.trellis/tasks/10-19-housing-catalog-coverage/desktop.png' });
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await page.getByText('第 2 / 2 页', { exact: true }).waitFor();
  await page.getByLabel('法拍数据筛选', { exact: true }).selectOption('has');
  await page.getByText('第 1 / 1 页', { exact: true }).waitFor();
  await page.getByLabel('租金状态筛选', { exact: true }).selectOption('data');
  await page.getByText('当前筛选：6 条', { exact: true }).waitFor();
  if (!requests.some(r => r.auction === 'has' && r.rental === 'data' && r.page === '1')) throw Error('组合筛选未发送或页码未重置');
  await page.locator('.catalog-data-link').first().click();
  await page.getByText('示例房产二拍', { exact: true }).waitFor();
  await page.getByText('示例更新失败，保留旧数据', { exact: true }).waitFor();
  await page.getByRole('dialog').getByRole('button', { name: '关闭', exact: true }).first().click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: '.trellis/tasks/10-19-housing-catalog-coverage/mobile.png' });
  const overflow = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: innerWidth }));
  if (overflow.scroll > overflow.width) throw Error(`窄屏页面溢出: ${JSON.stringify(overflow)}`);
  await page.getByRole('button', { name: '不收录（0）', exact: true }).click();
  await page.getByText('没有符合条件的记录。', { exact: true }).waitFor();
  console.log(JSON.stringify({ passed: true, desktop: '1440x1050', mobile: '390x844', combinedFilterAndPagination: true, detail: true, excludedTab: true, overflow }));
}
