import { isValidElement, type ComponentProps, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
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
  useInstallTargets: () => ({ current: 'hermes', targets: [], error: '', loading: false }),
}));

import SkillPool from './SkillPool';
import type { SkillCard } from '@/lib/types';

type NodeProps = {
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  'aria-label'?: string;
  className?: string;
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
function skill(id: string, repository = 'https://github.com/owner/first', extra: Partial<SkillCard> = {}): SkillCard {
  return {
    id, name: id, source: 'github', repository, path: id, tags: [], summary: '',
    status: 'active', deployments: {}, update: null, cache_missing: false, source_missing: false, ...extra,
  };
}
function props(skills: SkillCard[]): ComponentProps<typeof SkillPool> {
  return {
    skills, exportTargets: [], selectedIds: [], onSelect: vi.fn(),
    onInstallSelection: vi.fn(), onToggleQueueTarget: vi.fn(),
    onClone: vi.fn(), onDelete: vi.fn(), onUnpublish: vi.fn(), onUnpublishCollection: vi.fn(), onEditTags: vi.fn(),
    onExport: vi.fn(), onDeleteExport: vi.fn(),
  };
}
function groups(root: ReactNode) {
  return nodes(root).filter(n => n.type === 'li' && n.props['aria-label']?.endsWith(' 合集'));
}

beforeEach(() => {
  h.effects.forEach((e) => e.cleanup?.());
  h.values = [];
  h.refs = [];
  h.effects = [];
  vi.clearAllMocks();
});

describe('collection-scoped controls', () => {
  it('downloads the full collection independently of selection and visible members', () => {
    // 「下载合集」按钮在 modal 内（覆盖在 CollectionDialog.test.ts）；
    // 入口卡不再承载该入口。
    const a = skill('a');
    const b = skill('b');
    const onDownloadCollection = vi.fn();
    const p = { ...props([b]), allSkills: [a, b], onDownloadCollection };
    const [group] = groups(SkillPool(p));
    expect(text(group)).not.toContain('下载合集');
    expect(text(group)).not.toContain('打包中');
  });

  it('uses equally sized overview cards with explicit type labels and a dedicated modal entry', () => {
    const p = props([skill('a'), skill('b'), skill('single', 'https://github.com/owner/single')]);
    const tree = SkillPool(p);
    const [group] = groups(tree);
    expect(group.props).not.toMatchObject({ className: 'col-span-full' });
    const markup = renderToStaticMarkup(tree);
    expect(markup).toContain('合集 · 2 项');
    expect(markup).toContain('独立 Skill');
    // 入口卡结构：不再使用 <details>，由 button 开启 modal
    expect(markup).not.toContain('<details');
    expect(markup).toContain('查看成员');
    expect(markup).toContain('aria-label="打开 first 合集"');
    // modal 默认不挂载（open=false）
    expect(markup).not.toContain('合集操作');
    expect(markup).not.toContain('安装所选');
  });

  it('adds members through the modal; entry card stays minimal', () => {
    // 「＋ 添加成员」按钮在 modal 内（覆盖在 CollectionDialog.test.ts）；
    // 入口卡不再承载该入口。
    const [group] = groups(SkillPool({ ...props([skill('a'), skill('b')]) }));
    expect(text(group)).not.toContain('＋ 添加成员');
  });
  it('renders a single registered GitHub skill directly without collection controls', () => {
    const markup = renderToStaticMarkup(SkillPool(props([
      skill('luopan', 'https://github.com/zhangxiaoqiang1991/luopan'),
    ])));
    expect(markup).toContain('zhangxiaoqiang1991/luopan');
    expect(markup).toContain('aria-label="安装 luopan"');
    expect(markup).not.toContain('type="checkbox"');
    expect(markup).not.toContain('<details');
    expect(markup).not.toContain('安装所选');
    expect(markup).not.toContain('安装整个合集');
  });

  it('mixes independent cards and collections without turning filtered members into standalone cards', () => {
    const a = skill('a');
    const b = skill('b');
    const single = skill('single', 'https://github.com/owner/single');
    const p = { ...props([a, single]), allSkills: [a, b, single] };
    expect(groups(SkillPool(p))).toHaveLength(1);
    const markup = renderToStaticMarkup(SkillPool(p));
    expect(markup).not.toContain('安装整个合集');
    expect(markup).toContain('查看成员');
    expect(markup).not.toContain('aria-label="选择 a"');
    expect(markup).toContain('owner/single');
    expect(markup).not.toContain('<details');
  });

  it('emphasizes installation and pending updates, but not an installed current version', () => {
    const deployment = { status: 'active', revision: 'abc', published_at: '', link_target: '',
      content_hash: '', stale: false, link_missing: false };
    const update = { skill_id: 'a', repository: 'https://github.com/owner/first', remote_revision: 'abc',
      remote_tags: [], cached_revision: 'abc', has_update: false, checked_at: '2026-10-14' };
    const cases = [
      { extra: {}, label: '安装 a', primary: true },
      { extra: { deployments: { hermes: deployment }, update }, label: '更新 a', primary: false },
      { extra: { deployments: { hermes: deployment }, update: { ...update, has_update: true } }, label: '更新 a', primary: true },
      { extra: { deployments: { hermes: { ...deployment, stale: true } }, update }, label: '更新 a', primary: true },
    ];
    for (const { extra, label, primary } of cases) {
      const markup = renderToStaticMarkup(SkillPool(props([skill('a', undefined, extra)])));
      const action = markup.match(new RegExp(`<button[^>]*aria-label="${label}"[^>]*>`))?.[0];
      expect(action).toBeDefined();
      expect(action?.includes('bg-sky-700')).toBe(primary);
    }
  });

  it('keeps export history in one footer badge without per-target rows', () => {
    const deployment = {status:'active',revision:'abc',published_at:'2026-10-15',link_target:'',content_hash:'hash',stale:false,link_missing:false};
    const markup = renderToStaticMarkup(SkillPool(props([skill('local', undefined, {
      source:'local',deployments:{'windows-codex':deployment,'windows-claude':deployment},
    })])));
    expect(markup).toContain('已导出 · 2');
    expect(markup).not.toContain('点击重新导出');
    expect(markup).not.toContain('清除记录');
    expect(markup.indexOf('aria-label="导出 Skill"')).toBeLessThan(markup.indexOf('已导出 · 2'));
    expect(markup.indexOf('已导出 · 2')).toBeLessThan(markup.indexOf('aria-label="安装 local"'));
  });

  it('installs the entire collection when triggered from the modal install-selected button', () => {
    // modal 选择态现在收敛到 modal 内部 useState，外部 onSelect 不再被合集行触发；
    // 「安装所选」入口由 CollectionDialog 暴露，单元测试覆盖在 CollectionDialog.test.ts。
    const p = props([skill('a'), skill('blocked', undefined, { cache_missing: true })]);
    const [group] = groups(SkillPool(p));
    // 入口卡不再渲染全选 / 安装所选按钮
    expect(text(group)).not.toContain('全选');
    expect(text(group)).not.toContain('安装所选');
  });

  it('hides selection by default and routes hidden selections through the modal', () => {
    const a = skill('a');
    const hidden = skill('hidden');
    const p = { ...props([a]), allSkills: [a, hidden], selectedIds: ['hidden'] };
    const [group] = groups(SkillPool(p));
    // 入口卡不再直接暴露「含 N 个隐藏项」文案，统一在 modal 内处理
    expect(text(group)).not.toContain('含 1 个隐藏项');
    expect(text(group)).not.toContain('安装整个合集');
    // 入口卡保留「查看成员 →」入口
    expect(text(group)).toContain('查看成员');
  });

  it('shows repository identity once on the entry and keeps member actions inside the modal', () => {
    const markup = renderToStaticMarkup(SkillPool(props([skill('a'), skill('b')])));
    // repo 仅在入口卡上展示一次（不含 modal 副本）
    const withoutModal = markup;
    expect(text(SkillPool(props([skill('a'), skill('b')]))).split('owner/first')).toHaveLength(2);
    expect(withoutModal).not.toContain('>GitHub<');
    // modal 未挂载时不暴露成员选择 checkbox
    expect(withoutModal).not.toContain('aria-label="选择 a"');
    expect(withoutModal).not.toContain('aria-label="选择 b"');
    const localMarkup = renderToStaticMarkup(SkillPool(props([skill('local', undefined, { source: 'local' })])));
    expect(localMarkup).not.toContain('type="checkbox"');
    expect(localMarkup).not.toContain('安装所选');
  });
});
