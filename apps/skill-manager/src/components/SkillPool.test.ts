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
    onInstallSelection: vi.fn(), onAddCollection: vi.fn(), onToggleQueueTarget: vi.fn(),
    onClone: vi.fn(), onDelete: vi.fn(), onUnpublish: vi.fn(), onEditTags: vi.fn(),
    onExport: vi.fn(), onDeleteExport: vi.fn() };
}
function groups(root: ReactNode) {
  return nodes(root).filter(n => n.type === 'li' && n.props['aria-label']?.endsWith(' 合集'));
}

describe('collection-scoped controls', () => {
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

  it('makes hidden selections explicit and keeps whole-collection installation intact', () => {
    const a = skill('a');
    const hidden = skill('hidden');
    const p = { ...props([a]), allSkills: [a, hidden], selectedIds: ['hidden'] };
    const [group] = groups(SkillPool(p));
    expect(text(group)).toContain('含 1 个隐藏项');
    button(group, '全选匹配项').props.onClick!();
    expect(p.onSelect).toHaveBeenCalledExactlyOnceWith('a', true);
    button(group, '安装所选（1）').props.onClick!();
    expect(p.onInstallSelection).toHaveBeenCalledWith(['hidden']);
    button(group, '安装整个合集（2）').props.onClick!();
    expect(vi.mocked(p.onAddCollection!).mock.calls[0][0].members.map(s => s.id)).toEqual(['a', 'hidden']);
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
