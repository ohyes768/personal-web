import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ExportDialog from './ExportDialog';
import type { ExportTarget, SkillCard } from '../lib/types';

const skill: SkillCard = {
  id: 'alpha',
  name: 'Alpha',
  source: 'local',
  path: 'alpha',
  repository: null,
  update: null,
  tags: [],
  summary: '',
  status: 'active',
  deployments: {},
  cache_missing: false,
  source_missing: false,
};
const targets: ExportTarget[] = [
  {
    id: 'custom',
    name: '工作笔记本',
    install_path: '~/.codex/skills',
    notes: '离线解压',
    enabled: true,
    deployment_count: 1,
  },
  {
    id: 'disabled',
    name: '旧电脑',
    install_path: '',
    notes: '',
    enabled: false,
    deployment_count: 1,
  },
];
function render(overrides: Partial<Parameters<typeof ExportDialog>[0]> = {}) {
  return renderToStaticMarkup(
    createElement(ExportDialog, {
      skill,
      targets,
      busy: false,
      error: '',
      targetsError: '',
      onManageTargets() {},
      onConfirm() {},
      onClose() {},
      ...overrides,
    })
  );
}
describe('export target dialog', () => {
  it('uses enabled dynamic targets and shows installation instructions', () => {
    const html = render({ initialTarget: 'disabled' });
    expect(html).toContain('工作笔记本');
    expect(html).toContain('~/.codex/skills');
    expect(html).toContain('离线解压');
    expect(html).not.toContain('旧电脑');
    expect(html).toMatch(/checked=""[^>]*value="custom"/);
  });
  it('disables download and links to management when no targets are enabled', () => {
    const html = render({ targets: [] });
    expect(html).toContain('没有启用的导出目标');
    expect(html).toContain('管理导出目标');
    expect(html).toMatch(/type="submit" disabled=""/);
  });
  it('distinguishes load failure and allows cleanup for disabled targets', () => {
    expect(render({ targetsError: '加载失败' })).toContain('加载失败');
    expect(render({ targetsError: '加载失败' })).toMatch(
      /type="submit" disabled=""/
    );
    const html = render({ removing: 'disabled' });
    expect(html).toContain('清除 旧电脑');
    expect(html).not.toMatch(/type="submit" disabled=""/);
  });
});
