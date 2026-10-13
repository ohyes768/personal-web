import { isValidElement, type ReactNode, type ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TaskSnapshot } from '../lib/types';
const poll = vi.hoisted(() => ({ task: null as TaskSnapshot | null, error: '' }));
vi.mock('react', async (original) => ({ ...await original<typeof import('react')>(), useState: () => [0, () => {}], useRef: () => ({ current: false }), useEffect: () => {} }));
vi.mock('@/lib/useGithubTask', () => ({ useGithubTask: () => poll }));
import TaskProgressDialog from './TaskProgressDialog';
type Props = { children?: ReactNode; onClick?: () => void };
function nodes(node: ReactNode): ReactElement<Props>[] { if (Array.isArray(node)) return node.flatMap(nodes); if (!isValidElement<Props>(node)) return []; return [node, ...nodes(node.props.children)]; }
function text(node: ReactNode): string { if (Array.isArray(node)) return node.map(text).join(''); if (isValidElement<Props>(node)) return text(node.props.children); return typeof node === 'string' || typeof node === 'number' ? String(node) : ''; }
function snapshot(overrides: Partial<TaskSnapshot> = {}): TaskSnapshot { return { task_id: 'pack', kind: 'install_pack', repository: 'owner/repo', skill_id: null, state: 'done', stage: 'done', progress_percent: 100, progress_detail: '', error_code: null, error_message: null, created_at: '', updated_at: '', candidates: [], top_level: [], referenced_paths: [], results: [], ...overrides }; }
beforeEach(() => { poll.task = null; poll.error = ''; });
describe('pack task feedback', () => {
  it('displays per-target blocked results until the user acknowledges completion', () => {
    poll.task = snapshot({ result: { items: [{ target: 'hermes', status: 'success', message: '链接已创建' }, { target: 'openclaw', status: 'blocked', message: '目标不支持递归扫描' }] } });
    const onDone = vi.fn(); const tree = TaskProgressDialog({ taskId: 'pack', title: '安装包', onDone, onClose() {} });
    expect(text(tree)).toContain('目标不支持递归扫描');
    expect(onDone).not.toHaveBeenCalled();
    nodes(tree).find((node) => node.type === 'button' && text(node) === '完成')!.props.onClick!();
    expect(onDone).toHaveBeenCalledWith(poll.task);
  });
  it('displays prepared repository inventory count rather than registration children', () => {
    poll.task = snapshot({ kind: 'prepare_pack', result: { pack: { name: 'Repo', skill_count: 22 } as never } });
    expect(text(TaskProgressDialog({ taskId: 'pack', title: '添加包', onDone() {}, onClose() {} }))).toContain('Repo（22 个技能）');
  });
  it('shows polling failure and allows closing to retry from the workspace', () => {
    poll.error = '任务已失效'; const onClose = vi.fn(); const tree = TaskProgressDialog({ taskId: 'gone', title: '更新包', onDone() {}, onClose });
    expect(text(tree)).toContain('任务已失效');
    nodes(tree).find((node) => node.type === 'button' && text(node) === '关闭')!.props.onClick!();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
