import { createElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({
  values: [] as unknown[],
  refs: [] as {current: unknown}[],
  effects: [] as {deps: unknown[]; cleanup?: () => void}[],
  i: 0,
  r: 0,
  e: 0,
  select: vi.fn(),
  manage: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  useState(initial: unknown) {
    const i = h.i++;
    if (!(i in h.values)) h.values[i] = typeof initial === 'function' ? (initial as () => unknown)() : initial;
    return [
      h.values[i],
      (value: unknown) => {
        h.values[i] = typeof value === 'function' ? (value as (prev: unknown) => unknown)(h.values[i]) : value;
      },
    ];
  },
  useRef(initial: unknown) {
    const i = h.r++;
    return h.refs[i] ?? (h.refs[i] = { current: initial });
  },
  useEffect(effect: () => void | (() => void), deps: unknown[]) {
    const i = h.e++;
    const old = h.effects[i];
    if (!old || deps.some((d, j) => !Object.is(d, old.deps[j]))) {
      old?.cleanup?.();
      const cleanup = effect();
      h.effects[i] = { deps, cleanup: typeof cleanup === 'function' ? cleanup : undefined };
    }
  },
}));

import ProfileScopePicker from './ProfileScopePicker';
import type { InstallTarget } from '@/lib/installTargets';

type Props = {
  children?: ReactNode;
  description?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  'aria-label'?: string;
  'aria-expanded'?: boolean | string;
  'aria-haspopup'?: string;
};

function nodes(node: ReactNode): ReactElement<Props>[] {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!isValidElement<Props>(node)) return [];
  return [node, ...nodes(node.props.children), ...nodes(node.props.description)];
}

function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join('');
  if (isValidElement<Props>(node)) return text(node.props.children);
  return typeof node === 'string' || typeof node === 'number' ? String(node) : '';
}

function trigger(node: ReactNode): ReactElement<Props> {
  const result = nodes(node).find((n) => n.type === 'button' && n.props['aria-haspopup'] === 'dialog');
  if (!result) throw new Error('Missing trigger button');
  return result;
}

function button(node: ReactNode, label: string | RegExp): ReactElement<Props> {
  const result = nodes(node).find((n) => {
    if (n.type !== 'button') return false;
    const t = text(n);
    return typeof label === 'string' ? t === label : label.test(t);
  });
  if (!result) throw new Error(`Missing button: ${label}`);
  return result;
}

function markup(tree: ReactElement): string {
  return renderToStaticMarkup(createElement('div', null, tree));
}

const named = 'hermes:profile:ohyes768' as const;

const targets: InstallTarget[] = [
  {
    id: 'hermes',
    provider: 'hermes',
    profile_name: 'default',
    name: 'Default',
    install_path: '/targets/default',
    available: true,
    configured: true,
    unavailable_reason: '',
  },
  {
    id: named,
    provider: 'hermes',
    profile_name: 'ohyes768',
    name: 'ohyes768 dev',
    install_path: '/targets/ohyes768',
    available: true,
    configured: true,
    unavailable_reason: '',
    active_installation_count: 12,
  },
  {
    id: 'hermes:profile:archive',
    provider: 'hermes',
    profile_name: 'archive',
    name: 'archive',
    install_path: '/targets/archive',
    available: false,
    configured: true,
    unavailable_reason: '目录不可用：路径未挂载',
    active_installation_count: 0,
  },
];

const removedTarget: InstallTarget = {
  id: 'hermes:profile:gone',
  provider: 'hermes',
  profile_name: 'gone',
  name: 'gone dev',
  install_path: '/targets/gone',
  available: false,
  configured: true,
  unavailable_reason: '目标已移除',
  removed: true,
  active_installation_count: 0,
};
const removedTargets: InstallTarget[] = [...targets, removedTarget];

type PickerProps = Parameters<typeof ProfileScopePicker>[0];
function render(props: Partial<PickerProps> = {}): ReactElement {
  h.i = 0;
  h.r = 0;
  h.e = 0;
  // 直接以函数形式调用组件，返回已渲染的 JSX 树，供 nodes() 走查子节点；
  // 使用 createElement 只拿到外层包装，无法穿透进组件内部 JSX。
  return ProfileScopePicker({
    current: 'hermes',
    allTargets: targets,
    loading: false,
    error: '',
    onSelect: h.select,
    onManage: h.manage,
    onRefresh: h.refresh,
    ...props,
  } as PickerProps);
}

beforeEach(() => {
  h.effects.forEach((e) => e.cleanup?.());
  h.values = [];
  h.refs = [];
  h.effects = [];
  vi.clearAllMocks();
});

describe('ProfileScopePicker', () => {
  it('T1: available target renders green dot and provider · profile label, popover closed', () => {
    const tree = render({ current: 'hermes' });
    const m = markup(tree);
    expect(m).toContain('Hermes · default');
    expect(m).toContain('bg-emerald-500');
    expect(m).toContain('aria-expanded="false"');
    expect(m).not.toContain('切换发布目标');
  });

  it('T2: unavailable target renders amber border, amber dot, and reason in button label', () => {
    const tree = render({ current: 'hermes:profile:archive' });
    const m = markup(tree);
    expect(m).toContain('目标不可用');
    expect(m).toContain('目录不可用：路径未挂载');
    expect(m).toContain('border-amber-400');
    expect(m).toContain('bg-amber-500');
  });

  it('T3: loading state shows loading text without colored dot', () => {
    const tree = render({ loading: true, allTargets: [] });
    const m = markup(tree);
    expect(m).toContain('加载中');
    expect(m).toContain('animate-pulse');
    expect(m).not.toContain('bg-emerald-500');
  });

  it('T4: error state shows failure text, rose border and rose dot, triggers refresh on click', () => {
    const tree = render({ error: 'load failed', allTargets: [] });
    const m = markup(tree);
    expect(m).toContain('加载失败');
    expect(m).toContain('border-rose-400');
    expect(m).toContain('bg-rose-500');
    trigger(tree).props.onClick!();
    expect(h.refresh).toHaveBeenCalledOnce();
    // 不切换 popover
    const after = render({ error: 'load failed', allTargets: [] });
    expect(markup(after)).not.toContain('切换发布目标');
  });

  it('T5: invalid current id (not in targets) renders as invalid with amber styling', () => {
    const tree = render({ current: 'hermes:profile:nonexistent', allTargets: [] });
    const m = markup(tree);
    expect(m).toContain('hermes:profile:nonexistent');
    expect(m).toContain('不可用');
    expect(m).toContain('bg-amber-500');
  });

  it('T6: clicking trigger opens popover with title and refresh button', () => {
    const tree = render();
    expect(markup(tree)).not.toContain('切换发布目标');
    trigger(tree).props.onClick!();
    const open = render();
    const m = markup(open);
    expect(m).toContain('切换发布目标');
    expect(m).toContain('aria-expanded="true"');
    expect(m).toContain('管理安装目标');
  });

  it('T7: clicking popover item invokes onSelect and closes popover', () => {
    let tree = render();
    trigger(tree).props.onClick!();
    tree = render();
    button(tree, /Hermes · ohyes768/).props.onClick!();
    expect(h.select).toHaveBeenCalledExactlyOnceWith('hermes:profile:ohyes768');
    expect(markup(render())).not.toContain('切换发布目标');
  });

  it('T8: clicking footer manage link invokes onManage and closes popover', () => {
    let tree = render();
    trigger(tree).props.onClick!();
    tree = render();
    button(tree, /管理安装目标/).props.onClick!();
    expect(h.manage).toHaveBeenCalledOnce();
    expect(markup(render())).not.toContain('切换发布目标');
  });

  it('T9: clicking refresh button invokes onRefresh', () => {
    let tree = render();
    trigger(tree).props.onClick!();
    tree = render();
    button(tree, '刷新').props.onClick!();
    expect(h.refresh).toHaveBeenCalledOnce();
  });

  it('T10: popover items show install_path as monospace chip and active count, header does not', () => {
    let tree = render();
    expect(markup(tree)).not.toContain('/targets/ohyes768');
    trigger(tree).props.onClick!();
    tree = render();
    const m = markup(tree);
    expect(m).toContain('/targets/ohyes768');
    expect(m).toContain('已安装 12 个 Skill');
    expect(m).toContain('已安装 0 个 Skill');
    expect(m).toContain('font-mono');
  });

  it('T11: popover unavailable item shows unavailable_reason first line', () => {
    let tree = render();
    trigger(tree).props.onClick!();
    tree = render();
    const m = markup(tree);
    expect(m).toContain('路径未挂载');
  });

  it('T12: removed current target shows in button with gray dot, but not in popover list', () => {
    let tree = render({ current: 'hermes:profile:gone', allTargets: removedTargets });
    const m = markup(tree);
    expect(m).toContain('Hermes · gone');
    expect(m).toContain('已移除');
    expect(m).toContain('bg-slate-300');
    trigger(tree).props.onClick!();
    tree = render({ current: 'hermes:profile:gone', allTargets: removedTargets });
    const open = markup(tree);
    // 抽取 popover dialog 内容单独校验，避开 trigger button 上仍显示 removed 标识
    const dialog = open.match(/<div role="dialog"[^>]*>([\s\S]*)<\/div><\/div>$/);
    expect(dialog).not.toBeNull();
    const dialogHtml = dialog![1];
    expect(dialogHtml).not.toContain('gone');
    expect(dialogHtml).toContain('Hermes · default');
    expect(dialogHtml).toContain('Hermes · ohyes768');
  });

  it('T13: clicking trigger again toggles popover closed', () => {
    let tree = render();
    trigger(tree).props.onClick!();
    tree = render();
    expect(markup(tree)).toContain('切换发布目标');
    trigger(tree).props.onClick!();
    tree = render();
    expect(markup(tree)).not.toContain('切换发布目标');
  });

  it('T14: popover shows empty state when no visible targets', () => {
    let tree = render({ allTargets: [removedTarget] });
    trigger(tree).props.onClick!();
    tree = render({ allTargets: [removedTarget] });
    expect(markup(tree)).toContain('暂无 profile');
  });

  it('T15: active item gets sky background and sky border via data-active', () => {
    let tree = render({ current: 'hermes' });
    trigger(tree).props.onClick!();
    tree = render({ current: 'hermes' });
    const m = markup(tree);
    expect(m).toContain('data-active="true"');
    expect(m).toContain('data-[active=true]:border-sky-500');
    expect(m).toContain('data-[active=true]:bg-sky-50');
  });
});
