import { isValidElement, type ReactNode, type ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GithubPack } from '../lib/types';

const hooks = vi.hoisted(() => ({ values: [] as unknown[], refs: [] as { current: unknown }[], index: 0, refIndex: 0, add: vi.fn(), plan: vi.fn() }));
vi.mock('react', async (original) => ({
  ...await original<typeof import('react')>(),
  useState(initial: unknown) { const index = hooks.index++; if (!(index in hooks.values)) hooks.values[index] = initial; return [hooks.values[index], (next: unknown) => { hooks.values[index] = typeof next === 'function' ? next(hooks.values[index]) : next; }]; },
  useRef(initial: unknown) { const index = hooks.refIndex++; return hooks.refs[index] ?? (hooks.refs[index] = { current: initial }); },
}));
vi.mock('@/lib/api', async (original) => ({ ...await original<typeof import('../lib/api')>(), addGithubPack: hooks.add, planGithubPack: hooks.plan }));
import PackWorkspace from './PackWorkspace';
import ConfirmActionDialog from './ConfirmActionDialog';

type Props = { children?: ReactNode; type?: string; onClick?: () => Promise<void>; onChange?: (event: { target: { value: string } }) => void; onConfirm?: (password: string) => Promise<void>; busy?: boolean; error?: string; description?: ReactNode; disabled?: boolean; confirmDisabled?: boolean };
function nodes(node: ReactNode): ReactElement<Props>[] { if (Array.isArray(node)) return node.flatMap(nodes); if (!isValidElement<Props>(node)) return []; return [node, ...nodes(node.props.children), ...nodes(node.props.description)]; }
function text(node: ReactNode): string { if (Array.isArray(node)) return node.map(text).join(''); if (isValidElement<Props>(node)) return text(node.props.children); return typeof node === 'string' || typeof node === 'number' ? String(node) : ''; }
function render(packs: GithubPack[] = []) { hooks.index = 0; hooks.refIndex = 0; return PackWorkspace({ packs, loading: false, error: '', onRefresh: async () => {} }); }
function button(tree: ReactNode, label: string) { return nodes(tree).find((node) => node.type === 'button' && text(node) === label)!; }
function confirm(tree: ReactNode) { return nodes(tree).find((node) => node.type === ConfirmActionDialog)!; }
function addForm() { button(render(), '添加仓库包').props.onClick!(); const tree = render(); nodes(tree).find((node) => node.props.type === 'url')!.props.onChange!({ target: { value: 'https://github.com/owner/repo' } }); return confirm(render()); }
beforeEach(() => { hooks.values = []; hooks.refs = []; hooks.add.mockReset(); hooks.plan.mockReset(); });
describe('repository pack flow', () => {
  it('blocks duplicate submission while waiting for 202 and then transfers to task progress', async () => {
    let finish!: (value: { task_id: string; kind: string }) => void;
    hooks.add.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const pending = addForm().props.onConfirm!('secret');
    expect(confirm(render()).props.busy).toBe(true);
    await confirm(render()).props.onConfirm!('secret');
    expect(hooks.add).toHaveBeenCalledTimes(1);
    expect(hooks.add).toHaveBeenCalledWith({ repository: 'https://github.com/owner/repo', summary: '', tags: [] }, 'secret');
    finish({ task_id: 'pack-task', kind: 'prepare_pack' }); await pending;
    expect(nodes(render()).some((node) => node.type === ConfirmActionDialog)).toBe(false);
  });
  it('keeps the add form retryable after synchronous password or repository errors', async () => {
    hooks.add.mockRejectedValueOnce(new Error('密码错误'));
    await addForm().props.onConfirm!('wrong');
    expect(confirm(render()).props.busy).toBe(false);
    expect(confirm(render()).props.error).toBe('密码错误');
    hooks.add.mockResolvedValue({ task_id: 'retry', kind: 'prepare_pack' });
    await confirm(render()).props.onConfirm!('correct');
    expect(hooks.add).toHaveBeenCalledTimes(2);
  });
  it('keeps a blocked conversion preview cancellable and refuses confirmation', async () => {
    const pack = { id: 'repo', name: 'Repo', repository: 'owner/repo', skill_count: 13, tags: [], inventory: [{ name: 'A', path: 'skills/a', description: 'Readonly' }], deployments: {}, diagnostics: [] } as unknown as GithubPack;
    hooks.plan.mockResolvedValue({ items: [{ target: 'hermes', action: 'blocked', message: '未知目录冲突', legacy_skill_ids: [] }] });
    await button(render([pack]), '预览安装 / 转换').props.onClick!();
    const dialog = confirm(render([pack]));
    expect(dialog.props.busy).toBe(false);
    expect(dialog.props.confirmDisabled).toBe(true);
    expect(text(dialog.props.description)).toContain('全部 13 个技能');
    expect(text(dialog.props.description)).toContain('未知目录冲突');
    expect(nodes(render([pack])).filter((node) => node.props.type === 'checkbox')).toHaveLength(2);
    expect(text(render([pack]))).not.toContain('导出');
  });
});


