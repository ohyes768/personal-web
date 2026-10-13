import { isValidElement, type ReactElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({ values: [] as unknown[], refs: [] as {current: unknown}[], effects: [] as {deps: unknown[]; cleanup?: () => void}[], index: 0, refIndex: 0, effectIndex: 0,
  preview: vi.fn(), execute: vi.fn(), get: vi.fn(), refresh: vi.fn() }));
vi.mock('react', async original => ({...await original<typeof import('react')>(),
  useState(initial: unknown) { const i = hooks.index++; if (!(i in hooks.values)) hooks.values[i] = typeof initial === 'function' ? initial() : initial; return [hooks.values[i], (value: unknown) => { hooks.values[i] = typeof value === 'function' ? value(hooks.values[i]) : value; }]; },
  useRef(initial: unknown) { const i = hooks.refIndex++; return hooks.refs[i] ?? (hooks.refs[i] = {current: initial}); },
  useEffect(effect: () => void | (() => void), deps: unknown[]) { const i = hooks.effectIndex++; const old = hooks.effects[i]; if (!old || deps.some((d,j) => !Object.is(d,old.deps[j]))) { old?.cleanup?.(); const cleanup = effect(); hooks.effects[i] = {deps, cleanup: typeof cleanup === 'function' ? cleanup : undefined}; } }
}));
vi.mock('@/lib/api', () => ({previewInstall: hooks.preview, executeInstall: hooks.execute, getInstallTask: hooks.get}));
import InstallDialog from './InstallDialog';
type Props = { children?: ReactNode; description?: ReactNode; busy?: boolean; completed?: boolean; onConfirm?: (password: string) => Promise<void>; onClick?: () => void; error?: string };
function nodes(node: ReactNode): ReactElement<Props>[] { if (Array.isArray(node)) return node.flatMap(nodes); if (!isValidElement<Props>(node)) return []; return [node,...nodes(node.props.description),...nodes(node.props.children)]; }
function render() { hooks.index=0; hooks.refIndex=0; hooks.effectIndex=0; return InstallDialog({input:{skill_ids:['a','b']},onClose(){},onRefresh:hooks.refresh}); }
const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
beforeEach(() => { hooks.effects.forEach(e => e.cleanup?.()); hooks.values=[]; hooks.refs=[]; hooks.effects=[]; vi.clearAllMocks(); hooks.preview.mockResolvedValue({plan_id:'p',items:[{skill_id:'a',name:'A',action:'add'},{skill_id:'b',name:'B',action:'update'}]}); hooks.execute.mockResolvedValue({task_id:'t'}); hooks.get.mockResolvedValue({task_id:'t',state:'done',stage:'done',results:[{skill_id:'a',name:'A',status:'success',registered:true,error:''},{skill_id:'b',name:'B',status:'error',registered:true,error:'failed'}]}); hooks.refresh.mockResolvedValue(undefined); });
describe('Hermes unified install', () => {
  it('previews automatically, confirms once and retries only failures', async () => {
    render(); await flush(); const dialog=render();
    expect(hooks.preview).toHaveBeenCalledWith({skill_ids:['a','b']});
    expect(dialog.props.busy).toBe(false);
    dialog.props.onConfirm!('password'); dialog.props.onConfirm!('password'); await flush();
    expect(hooks.execute).toHaveBeenCalledTimes(1);
    expect(hooks.execute.mock.calls[0][0]).toBe('p');
    expect(JSON.stringify(hooks.preview.mock.calls)).not.toContain('password');
    render(); await flush(); const finished=render();
    expect(finished.props.completed).toBe(true);
    nodes(finished).find(n => n.type === 'button')!.props.onClick!();
    render(); await flush(); render();
    expect(hooks.preview).toHaveBeenLastCalledWith({skill_ids:['b']});
    expect(hooks.refresh).toHaveBeenCalledTimes(1);
  });
  it('reports lost task without automatically executing another install', async () => {
    hooks.get.mockRejectedValue(new Error('task_not_found'));
    render(); await flush(); render().props.onConfirm!('password'); await flush(); render(); await flush();
    expect(render().props.error).toBe('task_not_found');
    expect(hooks.execute).toHaveBeenCalledTimes(1);
  });
  it('all unchanged or blocked results allow closing without another password', async () => {
    hooks.preview.mockResolvedValue({plan_id:'p',items:[{skill_id:'a',name:'A',action:'unchanged'}]});
    render(); await flush(); const dialog=render();
    expect(dialog.props.completed).toBe(true);
    expect(dialog.props.busy).toBe(false);
    expect(hooks.execute).not.toHaveBeenCalled();
  });
});
