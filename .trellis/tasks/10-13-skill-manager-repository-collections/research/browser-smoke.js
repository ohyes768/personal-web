async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const deployment = { status: 'active', revision: '1234567890', published_at: '2026-10-13T08:00:00Z', link_target: '/fixture', link_missing: false, stale: false, content_hash: '' };
  const make = (id, repository, deployed = false) => ({ id, name: id, source: 'github', repository, path: `skills/${id}`, tags: [], summary: '', status: 'active', deployments: deployed ? { hermes: { ...deployment } } : {}, update: null, cache_missing: false, source_missing: false });
  const skills = [make('alpha', 'https://github.com/owner/ai-berkshire', true), make('beta', 'https://github.com/OWNER/ai-berkshire.git', true), make('design', 'https://github.com/Leonxlnx/taste-skill')];
  let failBeta = true;
  const deletions = [];
  let registered = null;
  await page.unroute('**/api/**');
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = request.url().replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    const body = request.postDataJSON();
    let result = {}, status = 200;
    if (path === '/api/export-targets') result = { items: [] };
    else if (path === '/api/skills') result = { items: skills };
    else if (path === '/api/skills/check-updates') result = { items: body.skill_ids.map(id => ({ skill_id: id, result: 'ok', info: { skill_id: id, repository: skills.find(s => s.id === id).repository, remote_revision: 'new', cached_revision: 'old', remote_tags: [], has_update: true, checked_at: '' } })) };
    else if (request.method() === 'DELETE') {
      const id = path.split('/')[3];
      deletions.push(id);
      if (id === 'beta' && failBeta) { failBeta = false; status = 409; result = { code: 'conflict', message: 'fixture conflict' }; }
      else { skills.find(s => s.id === id).deployments.hermes = { ...deployment, status: 'removed' }; result = { skill_id: id, target: 'hermes', status: 'removed' }; }
    } else if (path === '/api/skills/github/scan') { status = 202; result = { task_id: 'fixture-scan', kind: 'scan' }; }
    else if (path === '/api/skills/github/tasks/fixture-scan') result = { task_id: 'fixture-scan', kind: 'scan', repository: 'https://github.com/owner/new', skill_id: null, state: 'done', stage: 'done', candidates: [{ path: 'skills/one', name: 'one', description: '' }, { path: 'skills/two', name: 'two', description: '' }], top_level: [], referenced_paths: [], results: [], progress_percent: 100, progress_detail: '', created_at: '', updated_at: '', error_code: null, error_message: null };
    else if (path === '/api/skills/github/batch') { registered = body; status = 202; result = { task_id: 'fixture-register', kind: 'register_batch' }; }
    else if (path === '/api/skills/github/tasks/fixture-register') result = { task_id: 'fixture-register', kind: 'register_batch', repository: 'https://github.com/owner/new', skill_id: null, state: 'done', stage: 'done', candidates: [], top_level: [], referenced_paths: [], results: [{ skill_id: 'one', path: 'skills/one', name: 'one', status: 'success' }, { skill_id: 'two', path: 'skills/two', name: 'two', status: 'success' }], progress_percent: 100, progress_detail: '', created_at: '', updated_at: '', error_code: null, error_message: null };
    else { status = 404; result = { code: 'unexpected_mock_request', message: path }; }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(result) });
  });
  await page.goto('http://localhost:3018/skills?view=manage&tab=github');
  await page.getByRole('heading', { name: 'ai-berkshire', exact: true }).waitFor();
  assert(await page.getByRole('heading', { name: 'ai-berkshire', exact: true }).count() === 1, 'same repository was not grouped');
  const workspace = page.locator('[data-source="github"]');
  await workspace.getByRole('searchbox').fill('beta');
  const collection = workspace.locator('li').filter({ has: page.getByRole('heading', { name: 'ai-berkshire', exact: true }) }).first();
  assert((await collection.textContent()).includes('匹配 1 个'), 'member filtering failed');
  const add = collection.getByRole('button', { name: '全部发布到 Hermes（2 项）', exact: true });
  await add.click(); await add.click();
  assert((await workspace.textContent()).includes('alpha'), 'filtered collection lost hidden member from queue');
  assert(await workspace.getByRole('heading', { name: '发布队列（2）', exact: true }).count() === 1, 'duplicate or missing queue members');
  await collection.getByRole('button', { name: '检查更新', exact: true }).click();
  await page.getByText('检查完成：2 个 Skill 有远端更新', { exact: true }).waitFor();
  await page.getByRole('button', { name: '部署看板', exact: true }).click();
  await page.getByRole('button', { name: '从 Hermes 全部下架（2 项）', exact: true }).click();
  let dialog = page.getByRole('dialog', { name: '确认下架', exact: true });
  await dialog.getByRole('textbox').count();
  await dialog.locator('input[type=password]').fill('fixture-only');
  await dialog.getByRole('button', { name: '确认下架', exact: true }).click();
  await dialog.getByText('fixture conflict', { exact: false }).waitFor();
  assert(deletions.join(',') === 'alpha,beta', 'initial unpublish scope incorrect');
  await dialog.locator('input[type=password]').fill('fixture-only');
  await dialog.getByRole('button', { name: '重试失败项', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '下架结果', exact: true });
  await dialog.getByRole('button', { name: '完成', exact: true }).waitFor();
  assert(deletions.join(',') === 'alpha,beta,beta', 'retry repeated successful member');
  await dialog.getByRole('button', { name: '完成', exact: true }).click();
  await page.goto('http://localhost:3018/skills?view=manage&tab=github');
  await page.getByRole('button', { name: '新增 GitHub Skill', exact: true }).click();
  const register = page.getByRole('dialog', { name: '新增 GitHub Skill', exact: true });
  await register.locator('input[type=url]').fill('https://github.com/owner/new');
  await register.getByRole('button', { name: '扫描', exact: true }).click();
  await register.getByText('已选择 2/2 个 Skill · 展开调整', { exact: true }).waitFor();
  assert(await register.locator('details[open]').count() === 0, 'candidate details should default to collapsed');
  await register.getByRole('button', { name: '下一步：密码确认', exact: true }).click();
  const password = page.getByRole('dialog', { name: '确认批量登记 2 个 GitHub Skill', exact: true });
  await password.locator('input[type=password]').fill('fixture-only');
  await password.getByRole('button', { name: '确认批量登记', exact: true }).click();
  await page.waitForTimeout(300);
  assert(registered && registered.items.length === 2, 'default collection registration omitted members');
  console.log('PASS: repository grouping, filtered full-collection queue, update check, partial unpublish/retry, default all-member registration.');
}
