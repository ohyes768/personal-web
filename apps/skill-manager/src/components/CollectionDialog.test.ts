import { isValidElement, type ReactElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  values: [] as unknown[],
  refs: [] as {current: unknown}[],
  effects: [] as {deps: unknown[]; cleanup?: () => void}[],
  i: 0,
  r: 0,
  e: 0,
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

vi.mock('@/lib/installTargets', async (original) => ({
  ...(await original<typeof import('@/lib/installTargets')>()),
  useInstallTargets: () => ({
    current: 'hermes',
    targets: [
      { id: 'hermes', provider: 'hermes', name: 'Hermes', profile_name: 'default', install_path: '/t/hermes', available: true, configured: true, unavailable_reason: '' },
    ],
    error: '',
    loading: false,
  }),
}));

import CollectionDialog from './CollectionDialog';
import { groupCollections } from '@/lib/collections';
import type { SkillCard } from '@/lib/types';

type NodeProps = {
  children?: ReactNode;
  onClick?: ((e?: unknown) => void) | undefined;
  disabled?: boolean;
  'aria-label'?: string;
  'aria-modal'?: boolean;
  role?: string;
  type?: string;
};
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
function findButton(root: ReactNode, label: string): ReactElement<NodeProps> | undefined {
  return nodes(root).find(n => n.type === 'button' && text(n) === label);
}
function button(root: ReactNode, label: string): ReactElement<NodeProps> {
  const result = findButton(root, label);
  if (!result) throw new Error(`Missing button: ${label}`);
  return result;
}
function buttonByAriaLabel(root: ReactNode, label: string): ReactElement<NodeProps> {
  const result = nodes(root).find(n => n.type === 'button' && n.props['aria-label'] === label);
  if (!result) throw new Error(`Missing button with aria-label: ${label}`);
  return result;
}

function skill(id: string, extra: Partial<SkillCard> = {}): SkillCard {
  return {
    id, name: id, source: 'github',
    repository: 'https://github.com/owner/first',
    path: id, tags: [], summary: `${id} summary`, status: 'active',
    deployments: {}, update: null, cache_missing: false, source_missing: false, ...extra,
  };
}

function propsFor(collection: Parameters<typeof CollectionDialog>[0]['collection']) {
  return {
    collection,
    open: true,
    onClose: vi.fn(),
    onInstallSelection: vi.fn(),
    onAddMembers: vi.fn(),
    onCheckCollection: vi.fn(),
    onDownloadCollection: vi.fn(),
    downloadingCollection: null,
    checkingUpdates: undefined,
    targets: [],
    queue: [],
    onToggleQueueTarget: vi.fn(),
    onClone: vi.fn(),
    onDelete: vi.fn(),
    onUnpublish: vi.fn(),
    onEditTags: vi.fn(),
    onExport: vi.fn(),
    onDeleteExport: vi.fn(),
  };
}

function renderDialog(collection: Parameters<typeof CollectionDialog>[0]['collection']) {
  // 重置 hooks 计数让单测之间互相独立
  h.i = 0;
  h.r = 0;
  h.e = 0;
  return CollectionDialog(propsFor(collection));
}

beforeEach(() => {
  h.effects.forEach((e) => e.cleanup?.());
  h.values = [];
  h.refs = [];
  h.effects = [];
  vi.clearAllMocks();
});

describe('collection modal', () => {
  it('T1: renders nothing when closed, full structure when open=true', () => {
    const collection = groupCollections([skill('a'), skill('b')], [skill('a'), skill('b')])[0];
    const closedTree = CollectionDialog({ ...propsFor(collection), open: false });
    expect(nodes(closedTree).length).toBe(0);
    const openTree = renderDialog(collection);
    expect(buttonByAriaLabel(openTree, '关闭').props['aria-label']).toBe('关闭');
    expect(text(openTree)).toContain('合集 · 2 项');
  });

  it('T2: select all / clear toggles the selectedIds set; selection count text reflects size', () => {
    const collection = groupCollections([skill('a'), skill('b'), skill('c')], [skill('a'), skill('b'), skill('c')])[0];
    const tree = renderDialog(collection);
    expect(text(tree)).toContain('已选 0 项');
    button(tree, '全选').props.onClick?.();
    const tree2 = renderDialog(collection);
    expect(text(tree2)).toContain('已选 3 项');
    button(tree2, '清空选择').props.onClick?.();
    const tree3 = renderDialog(collection);
    expect(text(tree3)).toContain('已选 0 项');
  });

  it('T3: install-selected button is disabled when N=0', () => {
    const collection = groupCollections([skill('a'), skill('b')], [skill('a'), skill('b')])[0];
    const tree = renderDialog(collection);
    const installBtn = button(tree, '安装所选 (0)');
    expect(installBtn.props.disabled).toBe(true);
  });

  it('T4: update-all installs every collection member', () => {
    const a = skill('a', { deployments: { hermes: { status: 'active', revision: 'r', published_at: '', link_target: '', content_hash: '', stale: false, link_missing: false } } });
    const b = skill('b');
    const collection = groupCollections([a, b], [a, b])[0];
    const onInstallSelection = vi.fn();
    const onClose = vi.fn();
    const tree = CollectionDialog({ ...propsFor(collection), onInstallSelection, onClose });
    const updateAll = button(tree, '更新整个');
    expect(updateAll.props.disabled).toBe(false);
    updateAll.props.onClick?.();
    expect(onInstallSelection).toHaveBeenCalledExactlyOnceWith([a.id, b.id]);
    expect(onClose).toHaveBeenCalled();
  });

  it('T5: per-member install / unpublish invokes callbacks and closes the modal', () => {
    const a = skill('a');
    const b = skill('b');
    const collection = groupCollections([a, b], [a, b])[0];
    const onToggleQueueTarget = vi.fn();
    const onUnpublish = vi.fn();
    const onClose = vi.fn();
    const tree = CollectionDialog({ ...propsFor(collection), onToggleQueueTarget, onUnpublish, onClose });
    buttonByAriaLabel(tree, '安装 a').props.onClick?.();
    expect(onToggleQueueTarget).toHaveBeenCalledExactlyOnceWith('a', 'hermes');
    expect(onClose).toHaveBeenCalledTimes(1);

    const installed = skill('installed', { deployments: { hermes: { status: 'active', revision: 'r', published_at: '', link_target: '', content_hash: '', stale: false, link_missing: false } } });
    const collection2 = groupCollections([installed], [installed])[0];
    const onUnpublish2 = vi.fn();
    const onClose2 = vi.fn();
    const tree2 = CollectionDialog({ ...propsFor(collection2), onUnpublish: onUnpublish2, onClose: onClose2 });
    buttonByAriaLabel(tree2, '下架 installed').props.onClick?.();
    expect(onUnpublish2).toHaveBeenCalledExactlyOnceWith('installed', 'installed', ['hermes']);
    expect(onClose2).toHaveBeenCalled();
  });

  it('T6: status chips (📦 / 🆕 / ⚠) only render when their count > 0', () => {
    const a = skill('a', { cache_missing: true });
    const b = skill('b');
    const collection = groupCollections([a, b], [a, b])[0];
    const tree = renderDialog(collection);
    // a cache_missing → ⚠ 异常 1 项 出现
    expect(text(tree)).toContain('⚠ 异常');
    expect(text(tree)).not.toContain('📦 已导出');
    expect(text(tree)).not.toContain('🆕 有更新');

    const u = skill('u', { update: { skill_id: 'u', repository: '', remote_revision: 'r2', remote_tags: [], cached_revision: 'r1', has_update: true, checked_at: '2026-10-15' } });
    const collection2 = groupCollections([u], [u])[0];
    const tree2 = renderDialog(collection2);
    expect(text(tree2)).toContain('🆕 有更新');
    expect(text(tree2)).not.toContain('⚠ 异常');

    const e = skill('e', { deployments: { export1: { status: 'active', revision: 'r', published_at: '', link_target: '', content_hash: '', stale: false, link_missing: false } } });
    const collection3 = groupCollections([e], [e])[0];
    const tree3 = renderDialog(collection3);
    expect(text(tree3)).toContain('📦 已导出');
    expect(text(tree3)).not.toContain('🆕 有更新');
  });

  it('T7: completed collection shows the green ✓ N/N 全部安装 label', () => {
    const installed = skill('a', { deployments: { hermes: { status: 'active', revision: 'r', published_at: '', link_target: '', content_hash: '', stale: false, link_missing: false } } });
    const installed2 = skill('b', { deployments: { hermes: { status: 'active', revision: 'r', published_at: '', link_target: '', content_hash: '', stale: false, link_missing: false } } });
    const collection = groupCollections([installed, installed2], [installed, installed2])[0];
    const tree = renderDialog(collection);
    expect(text(tree)).toContain('✓ 2/2 已全部安装');
  });

  it('T8: Esc key closes the dialog via the keydown handler', () => {
    const a = skill('a');
    const collection = groupCollections([a], [a])[0];
    const onClose = vi.fn();
    // 注入最小 document 暴露 collection 接口让 Esc 监听可被 spy
    const originalDocument = (globalThis as {document?: unknown}).document;
    const keydownListeners: Array<(e: KeyboardEvent) => unknown> = [];
    (globalThis as {document: { addEventListener: (k: string, l: (e: KeyboardEvent) => unknown) => void; removeEventListener: (k: string, l: (e: KeyboardEvent) => unknown) => void }}).document = {
      addEventListener(key, listener) { if (key === 'keydown') keydownListeners.push(listener as (e: KeyboardEvent) => unknown); },
      removeEventListener(key, listener) {
        if (key === 'keydown') {
          const i = keydownListeners.indexOf(listener as (e: KeyboardEvent) => unknown);
          if (i >= 0) keydownListeners.splice(i, 1);
        }
      },
    };
    try {
      CollectionDialog({ ...propsFor(collection), onClose });
      expect(keydownListeners).toHaveLength(1);
      keydownListeners[0]({ key: 'Escape' } as unknown as KeyboardEvent);
      expect(onClose).toHaveBeenCalled();
    } finally {
      (globalThis as {document?: unknown}).document = originalDocument;
    }
  });

  it('renders per-member update / unpublish labels matching deployment status', () => {
    const a = skill('not-installed');
    const b = skill('installed', { deployments: { hermes: { status: 'active', revision: 'r', published_at: '', link_target: '', content_hash: '', stale: false, link_missing: false } } });
    const collection = groupCollections([a, b], [a, b])[0];
    const tree = renderDialog(collection);
    expect(buttonByAriaLabel(tree, '安装 not-installed')).toBeDefined();
    expect(buttonByAriaLabel(tree, '更新 installed')).toBeDefined();
    expect(buttonByAriaLabel(tree, '下架 installed')).toBeDefined();
  });

  it('preserves export / update chip line when source-missing anomalies are absent', () => {
    const a = skill('a');
    const b = skill('b');
    const collection = groupCollections([a, b], [a, b])[0];
    const tree = renderDialog(collection);
    // 默认没有任何 chip
    expect(text(tree)).not.toContain('📦 已导出');
    expect(text(tree)).not.toContain('🆕 有更新');
    expect(text(tree)).not.toContain('⚠ 异常');
  });
});

describe('CollectionDialog useEffect listener wiring', () => {
  it('attaches a keydown listener while open and removes it on close', () => {
    const originalDocument = (globalThis as {document?: unknown}).document;
    const log: Array<{kind: 'add' | 'remove'; key: string}> = [];
    (globalThis as {document: { addEventListener: (k: string, l: unknown) => void; removeEventListener: (k: string, l: unknown) => void }}).document = {
      addEventListener(key) { log.push({kind: 'add', key}); },
      removeEventListener(key) { log.push({kind: 'remove', key}); },
    };
    try {
      const a = skill('a');
      const collection = groupCollections([a], [a])[0];
      CollectionDialog({ ...propsFor(collection) });
      expect(log.some(e => e.kind === 'add' && e.key === 'keydown')).toBe(true);
      h.effects.forEach((e) => e.cleanup?.());
      expect(log.some(e => e.kind === 'remove' && e.key === 'keydown')).toBe(true);
    } finally {
      (globalThis as {document?: unknown}).document = originalDocument;
    }
  });
});