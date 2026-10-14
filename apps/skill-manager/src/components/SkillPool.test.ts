import { isValidElement, type ComponentProps, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import SkillPool from './SkillPool';
import type { SkillCard } from '@/lib/types';

type NodeProps = { children?: ReactNode; onClick?: () => void; disabled?: boolean; 'aria-label'?: string };
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
function button(root: ReactNode, label: string) {
  const result = nodes(root).find(n => n.type === 'button' && text(n) === label);
  if (!result) throw new Error(`Missing button: ${label}`);
  return result;
}
function skill(id: string, repository = 'https://github.com/owner/first', extra: Partial<SkillCard> = {}): SkillCard {
  return { id, name: id, source: 'github', repository, path: id, tags: [], summary: '',
    status: 'active', deployments: {}, update: null, cache_missing: false, source_missing: false, ...extra };
}
function props(skills: SkillCard[]): ComponentProps<typeof SkillPool> {
  return { skills, queue: [], exportTargets: [], selectedIds: [], onSelect: vi.fn(),
    onInstallSelection: vi.fn(), onToggleQueueTarget: vi.fn(),
    onClone: vi.fn(), onDelete: vi.fn(), onUnpublish: vi.fn(), onEditTags: vi.fn(),
    onExport: vi.fn(), onDeleteExport: vi.fn() };
}
function groups(root: ReactNode) {
  return nodes(root).filter(n => n.type === 'li' && n.props['aria-label']?.endsWith(' 合集'));
}

describe('collection-scoped controls', () => {
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
    expect(markup).toContain('全选匹配项');
    expect(markup).toContain('aria-label="选择 a"');
    expect(markup).not.toContain('aria-label="选择 single"');
    expect(markup).toContain('owner/single');
    expect(markup.match(/<details/g)).toHaveLength(1);
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
      expect(action?.includes('bg-sky-600')).toBe(primary);
    }
  });

  it('selects and installs only this collection, skipping unavailable members', () => {
    const p = props([skill('a'), skill('blocked', undefined, { cache_missing: true }),
      skill('b', 'https://github.com/owner/second')]);
    const [first] = groups(SkillPool(p));
    button(first, '全选').props.onClick!();
    expect(p.onSelect).toHaveBeenCalledExactlyOnceWith('a', true);

    const selected = groups(SkillPool({ ...p, selectedIds: ['a', 'b', 'blocked'] }));
    button(selected[0], '安装所选（1）').props.onClick!();
    expect(p.onInstallSelection).toHaveBeenCalledExactlyOnceWith(['a']);
    vi.mocked(p.onSelect!).mockClear();
    button(selected[0], '清空选择').props.onClick!();
    expect(p.onSelect).toHaveBeenCalledWith('a', false);
    expect(p.onSelect).not.toHaveBeenCalledWith('b', false);
  });

  it('makes hidden selections explicit and installs only selected members', () => {
    const a = skill('a');
    const hidden = skill('hidden');
    const p = { ...props([a]), allSkills: [a, hidden], selectedIds: ['hidden'] };
    const [group] = groups(SkillPool(p));
    expect(text(group)).toContain('含 1 个隐藏项');
    button(group, '全选匹配项').props.onClick!();
    expect(p.onSelect).toHaveBeenCalledExactlyOnceWith('a', true);
    button(group, '安装所选（1）').props.onClick!();
    expect(p.onInstallSelection).toHaveBeenCalledWith(['hidden']);
    expect(text(group)).not.toContain('安装整个合集');
  });

  it('shows repository identity once and keeps member selection accessible', () => {
    const markup = renderToStaticMarkup(SkillPool(props([skill('a'), skill('b')])));
    expect(markup.split('owner/first')).toHaveLength(2);
    expect(markup).not.toContain('>GitHub<');
    expect(markup).toContain('aria-label="选择 a"');
    expect(markup).toContain('aria-label="选择 b"');
    const localMarkup = renderToStaticMarkup(SkillPool(props([skill('local', undefined, { source: 'local' })])));
    expect(localMarkup).not.toContain('type="checkbox"');
    expect(localMarkup).not.toContain('安装所选');
  });
});
