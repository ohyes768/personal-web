async page => {
  const results = [];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    results.push(await page.evaluate(() => {
      const row = [...document.querySelectorAll('.directory-task-row')].find(el => el.querySelector('strong')?.textContent === '匹配楼盘地点与类型');
      const dialog = document.querySelector('dialog');
      return { width: innerWidth, overflow: dialog.scrollWidth > dialog.clientWidth,
        buttons: [...row.querySelectorAll('button')].map(el => { const r = el.getBoundingClientRect(); return { text: el.textContent, left: Math.round(r.left), right: Math.round(r.right), visible: r.left >= 0 && r.right <= innerWidth }; }) };
    }));
    await page.screenshot({path: '.trellis/tasks/10-29-housing-position-refresh-all/research/controls-' + width + '.png'});
  }
  return results;
}
