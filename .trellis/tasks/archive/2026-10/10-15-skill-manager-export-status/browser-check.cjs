async (page) => {
  const deployment = {status:'active',revision:'abcdef123456',content_hash:'verified-content',published_at:'2026-10-15T15:00:00+08:00',link_target:'',link_missing:false,stale:false};
  const base = {source:'local',repository:null,path:'test',tags:['dev-workflow'],summary:'自动生成规范 commit message 并推送远程',status:'active',update:null,cache_missing:false,source_missing:false};
  const items = [
    {...base,id:'git-commit-push',name:'git-commit-push',deployments:{'windows-claude':deployment,'windows-codex':deployment}},
    {...base,id:'no-exports',name:'no-exports',deployments:{}},
    {...base,id:'stale-exports',name:'stale-exports',deployments:{'windows-claude':deployment,'windows-codex':{...deployment,stale:true}}},
  ];
  const targets = ['claude','codex'].map(id => ({id:`windows-${id}`,name:`Windows ${id === 'claude' ? 'Claude Code' : 'Codex'}`,install_path:'C:/skills',notes:'',enabled:true,deployment_count:2}));
  await page.unrouteAll({behavior:'ignoreErrors'});
  await page.route('**/api/**', route => {
    const path = route.request().url().split('localhost:3008')[1].split('?')[0];
    const body = path === '/api/export-targets' ? {items:targets} : path.endsWith('/install-targets') ? {items:[{id:'hermes',provider:'hermes',profile_name:'default',name:'默认环境',install_path:'/hermes/skills',configured:true,available:true,unavailable_reason:''}]} : {items};
    return route.fulfill({json:body});
  });
  await page.setViewportSize({width:1440,height:900});
  await page.goto('http://localhost:3008/skills');
  const badge = page.getByRole('button',{name:'git-commit-push 导出记录',exact:true});
  await badge.waitFor();
  const card = badge.locator('xpath=ancestor::li[1]');
  const emptyCard = page.getByRole('heading',{name:'no-exports',exact:true}).locator('xpath=ancestor::li[1]');
  const height = (await card.boundingBox()).height;
  const emptyHeight = (await emptyCard.boundingBox()).height;
  if (height !== emptyHeight) throw new Error(`Card height changed: ${height} vs ${emptyHeight}`);
  await badge.focus();
  await page.getByRole('tooltip').waitFor();
  if (!(await page.getByRole('tooltip').innerText()).includes('与当前源一致')) throw new Error('Missing source status');
  await badge.click();
  const dialog = page.getByRole('dialog',{name:'git-commit-push 导出记录',exact:true});
  await dialog.waitFor();
  if (!(await dialog.getByRole('button',{name:'关闭导出记录'}).evaluate(el=>el===document.activeElement))) throw new Error('Missing initial focus');
  await page.screenshot({path:'.trellis/tasks/10-15-skill-manager-export-status/desktop.png'});
  await page.keyboard.press('Escape');
  await dialog.waitFor({state:'hidden'});
  if (!(await badge.evaluate(el=>el===document.activeElement))) throw new Error('Focus not restored');
  await badge.click();
  await page.getByRole('heading',{name:'Skill 发布管理台'}).click();
  await dialog.waitFor({state:'hidden'});
  const stale = page.getByRole('button',{name:'stale-exports 导出记录',exact:true});
  if (await stale.innerText() !== '待更新 · 1') throw new Error('Wrong stale badge');
  await stale.click();
  const staleDialog = page.getByRole('dialog',{name:'stale-exports 导出记录',exact:true});
  await staleDialog.getByRole('button',{name:'重新导出到 Windows Codex'}).click();
  await page.getByRole('dialog',{name:'导出 Skill',exact:true}).waitFor();
  if (!(await page.getByRole('radio',{name:/Windows Codex/}).isChecked())) throw new Error('Wrong export target');
  await page.getByRole('button',{name:'取消',exact:true}).click();
  await badge.click();
  await dialog.getByRole('button',{name:'清除 Windows Claude Code 导出记录'}).click();
  await page.getByRole('dialog',{name:'清除导出记录',exact:true}).waitFor();
  await page.getByRole('button',{name:'取消',exact:true}).click();
  await page.setViewportSize({width:375,height:812});
  const mobileHeight = (await card.boundingBox()).height;
  const mobileEmptyHeight = (await emptyCard.boundingBox()).height;
  if (mobileHeight !== mobileEmptyHeight) throw new Error(`Mobile card height changed: ${mobileHeight} vs ${mobileEmptyHeight}`);
  await badge.scrollIntoViewIfNeeded();
  await badge.click();
  await dialog.waitFor();
  const bounds = await dialog.boundingBox();
  if (bounds.x < 0 || bounds.x + bounds.width > 375 || bounds.y < 0 || bounds.y + bounds.height > 812) throw new Error('Mobile popover overflows viewport');
  if (await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth)) throw new Error('Page has horizontal overflow');
  await page.screenshot({path:'.trellis/tasks/10-15-skill-manager-export-status/mobile.png'});
  await page.keyboard.press('Escape');
  return {desktopCardHeight:height,withoutExportsHeight:emptyHeight,mobileHeight,mobileEmptyHeight,mobilePopover:bounds,checks:['tooltip','focus','Escape','outside click','re-export target','clear confirmation','mobile bounds']};
}
