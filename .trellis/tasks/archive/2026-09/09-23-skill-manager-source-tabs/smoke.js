// 原型交互冒烟测试：入队 → 计划 → 发布弹窗 → tab 隔离
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));

  const url = 'file:///F:/personal-projects/personal-web/.trellis/tasks/09-23-skill-manager-source-tabs/prototype.html';
  await page.goto(url);

  // 1. 自研 tab：graphify 加入 OpenClaw 队列
  await page.click('[data-act="queue"][data-id="graphify"][data-target="openclaw"]');
  // 2. 生成计划
  await page.click('#panel-local [data-act="plan"]');
  const planOk = await page.locator('#panel-local .plan-item').count();
  console.log('plan items (local):', planOk);

  // 3. 切到 GitHub tab：队列应为空（隔离验证）
  await page.click('#sourceSeg [data-source="github"]');
  const ghQueueEmpty = await page.locator('#queueGithub .queue-empty').count();
  console.log('github queue empty after local enqueue:', ghQueueEmpty === 1);

  // 4. github 入队 + 计划
  await page.click('[data-act="queue"][data-id="anthropic-pdf"][data-target="hermes"]');
  await page.click('#panel-github [data-act="plan"]');
  console.log('plan items (github):', await page.locator('#panel-github .plan-item').count());

  // 5. 发布弹窗
  await page.click('#panel-github [data-act="publish"]');
  await page.waitForSelector('#modalMask.open');
  await page.screenshot({ path: 'shot-publish-dialog.png' });
  await page.fill('#mPwd', 'test123');
  await page.click('#mOk');
  await page.waitForTimeout(1100);
  const toastText = await page.locator('.toast-msg').first().textContent();
  console.log('publish toast:', toastText);

  // 6. 切回自研 tab：队列/计划应保留
  await page.click('#sourceSeg [data-source="local"]');
  const localPlanStill = await page.locator('#panel-local .plan-item').count();
  console.log('local plan preserved after tab switch:', localPlanStill === planOk);

  // 7. URL 同步
  await page.click('#sourceSeg [data-source="github"]');
  console.log('url after switch:', page.url());

  // 8. 检查更新按钮
  await page.click('#btnCheckUpdates');
  await page.waitForTimeout(1100);
  const updBadges = await page.locator('.badge.upd').count();
  console.log('update badges after check:', updBadges);

  // 9. 部署看板：直达、segmented 切换、筛选、下架
  await page.click('.tab[data-view="board"]');
  console.log('board url:', page.url());
  const ocRows = await page.locator('#boardList .deployed-row').count();
  console.log('board openclaw rows:', ocRows);
  await page.click('#boardSeg [data-target="hermes"]');
  const hmRows = await page.locator('#boardList .deployed-row').count();
  console.log('board hermes rows:', hmRows);
  await page.selectOption('#boardSource', 'github');
  const ghRows = await page.locator('#boardList .deployed-row').count();
  console.log('board hermes github rows:', ghRows);
  await page.selectOption('#boardSource', 'all');
  // 下架第一条
  const firstName = await page.locator('#boardList .deployed-row .skill-name').first().textContent();
  await page.click('#boardList [data-act="unpublish"]');
  await page.fill('#mPwd', 'x');
  await page.click('#mOk');
  await page.waitForTimeout(700);
  const hmRowsAfter = await page.locator('#boardList .deployed-row').count();
  console.log(`unpublish first (${firstName.trim()}): rows ${hmRows} -> ${hmRowsAfter}`);

  await page.screenshot({ path: 'shot-board.png' });
  console.log('pageerrors:', errors.length ? errors : 'none');
  await browser.close();
})();
