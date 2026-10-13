import { isValidElement, type ReactNode, type ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TaskSnapshot } from '../lib/types';

// Node 测试环境无 DOM；保留实际 JSX 树，以状态容器驱动重渲染并调用真实事件处理器。
const hooks = vi.hoisted(() => ({
  values: [] as unknown[], refs: [] as { current: unknown }[], index: 0, refIndex: 0,
  poll: { task: null as TaskSnapshot | null, error: '' },
  start: vi.fn(),
}));
vi.mock('react', async (original) => ({
  ...await original<typeof import('react')>(),
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (next: unknown) => {
      hooks.values[index] = typeof next === 'function'
        ? next(hooks.values[index]) : next;
    }];
  },
  useRef(initial: unknown) {
    const index = hooks.refIndex++;
    return hooks.refs[index] ?? (hooks.refs[index] = { current: initial });
  },
  useEffect() {},
}));
vi.mock('@/lib/api', () => ({ startGithubScan: hooks.start }));
vi.mock('@/lib/useGithubTask', () => ({ useGithubTask: () => hooks.poll }));
import RegisterGithubDialog from './RegisterGithubDialog';

type NodeProps = { children?: ReactNode; type?: string; onClick?: () => Promise<void>;
  onChange?: (event: { target: { value: string } }) => void; disabled?: boolean;
  role?: string; 'aria-busy'?: boolean; className?: string };
function nodes(node: ReactNode): ReactElement<NodeProps>[] {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!isValidElement<NodeProps>(node)) return [];
  return [node, ...nodes(node.props.children)];
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join('');
  if (isValidElement<NodeProps>(node)) return text(node.props.children);
  return typeof node === 'string' || typeof node === 'number' ? String(node) : '';
}
function render() {
  hooks.index = 0;
  hooks.refIndex = 0;
  return RegisterGithubDialog({ busy: false, onRegister() {}, onRegisterBatch() {}, onCancel() {} });
}
function scanButton(tree: ReactNode) {
  return nodes(tree).find((node) => node.type === 'button' && node.props.onClick)!;
}
function enterRepository() {
  nodes(render()).find((node) => node.props.type === 'url')!.props.onChange!(
    { target: { value: 'https://github.com/owner/repo' } }
  );
  return render();
}
function snapshot(overrides: Partial<TaskSnapshot> = {}): TaskSnapshot {
  return {
    task_id: 'scan-task', kind: 'scan', repository: 'https://github.com/owner/repo',
    skill_id: null, state: 'running', stage: 'receiving', progress_percent: 45,
    progress_detail: '12 MiB', error_code: null, error_message: null,
    created_at: '', updated_at: '', candidates: [], top_level: [],
    referenced_paths: [], results: [], ...overrides,
  };
}
beforeEach(() => {
  hooks.values = [];
  hooks.refs = [];
  hooks.poll = { task: null, error: '' };
  hooks.start.mockReset();
});
describe('GitHub scan loading', () => {
  it('shows immediate loading and blocks repeat clicks before the request resolves', async () => {
    let finish!: (value: { task_id: string; kind: string }) => void;
    hooks.start.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const button = scanButton(enterRepository());
    const pending = button.props.onClick!();
    const loading = render();
    expect(scanButton(loading).props.disabled).toBe(true);
    expect(text(loading)).toContain('准备扫描');
    expect(nodes(loading).some((node) => node.props.className?.includes('animate-spin'))).toBe(true);
    await button.props.onClick!();
    expect(hooks.start).toHaveBeenCalledTimes(1);
    finish({ task_id: 'new-task', kind: 'scan' });
    await pending;
    expect(scanButton(render()).props.disabled).toBe(true);
    expect(text(render())).toContain('扫描中');
  });
  it('restores the button after a submission failure and allows retry', async () => {
    hooks.start.mockRejectedValueOnce(new Error('仓库不可达'));
    await scanButton(enterRepository()).props.onClick!();
    expect(scanButton(render()).props.disabled).toBe(false);
    expect(text(render())).toContain('仓库不可达');
    hooks.start.mockResolvedValueOnce({ task_id: 'retry-task', kind: 'scan' });
    await scanButton(render()).props.onClick!();
    expect(hooks.start).toHaveBeenCalledTimes(2);
    expect(scanButton(render()).props.disabled).toBe(true);
  });
  it('stops loading when task polling fails', async () => {
    hooks.start.mockResolvedValue({ task_id: 'lost-task', kind: 'scan' });
    await scanButton(enterRepository()).props.onClick!();
    hooks.poll.error = '任务已失效';
    expect(scanButton(render()).props.disabled).toBe(false);
    expect(text(render())).toContain('任务已失效');
  });
  it('shows task progress and restores the button on completion', async () => {
    hooks.start.mockResolvedValue({ task_id: 'scan-task', kind: 'scan' });
    await scanButton(enterRepository()).props.onClick!();
    hooks.poll.task = snapshot();
    expect(text(render())).toContain('克隆中 45%');
    expect(text(render())).toContain('已用时');
    expect(text(render())).toContain('12 MiB');
    hooks.poll.task = snapshot({ state: 'done' });
    expect(scanButton(render()).props.disabled).toBe(false);
    expect(scanButton(render()).props['aria-busy']).toBe(false);
  });
  it('hides the previous result as soon as a new scan is submitted', async () => {
    hooks.start.mockResolvedValueOnce({ task_id: 'scan-task', kind: 'scan' });
    await scanButton(enterRepository()).props.onClick!();
    hooks.poll.task = snapshot({ state: 'done' });
    expect(text(render())).toContain('未在该仓库中找到');
    let finish!: (value: { task_id: string; kind: string }) => void;
    hooks.start.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = scanButton(render()).props.onClick!();
    expect(text(render())).not.toContain('未在该仓库中找到');
    expect(text(render())).toContain('准备扫描');
    finish({ task_id: 'next-task', kind: 'scan' });
    await pending;
  });
});
