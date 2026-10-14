'use client';

import { useMemo, useState } from 'react';
import InstallDialog from '@/components/InstallDialog';
import EditSkillTagsDialog from '@/components/EditSkillTagsDialog';
import ExportDialog from '@/components/ExportDialog';
import SkillFilters, { DEFAULT_FILTERS, type FilterState } from '@/components/SkillFilters';
import SkillPool from '@/components/SkillPool';
import { type SkillCollection } from '@/lib/collections';
import { ApiClientError, deleteExport, exportSkill, updateSkillTags } from '@/lib/api';
import type { ExportTargetKey } from '@/lib/targets';
import type { TargetKey } from '@/lib/queue';
import type { ExportTarget, SkillCard } from '@/lib/types';

export interface Notice {
  kind: 'ok' | 'err';
  text: string;
}

interface SourceWorkspaceProps {
  exportTargets: ExportTarget[];
  targetsError: string;
  onManageTargets: () => void;
  source: SkillCard['source'];
  skills: SkillCard[];
  loading: boolean;
  onRefresh: () => Promise<void>;
  onNotify: (notice: Notice | null) => void;
  onClone: (skillId: string, skillName: string) => void;
  onDelete: (skill: SkillCard) => void;
  onUnpublish: (skillId: string, skillName: string, targets: TargetKey[]) => void;
  onCheckUpdates?: (skillIds: string[]) => Promise<void>;
  checkingUpdates?: boolean;
}

function applyFilters(skills: SkillCard[], filters: FilterState): SkillCard[] {
  const query = filters.query.trim().toLowerCase();
  return skills.filter((skill) => {
    if (query) {
      const haystack = `${skill.name} ${skill.id} ${skill.summary} ${skill.repository ?? ''}`.toLowerCase();
      if (!haystack.includes(query)) {
        return false;
      }
    }
    if (filters.tags.some((tag) => !skill.tags.includes(tag))) {
      return false;
    }
    // Hermes 安装记录有效且链接存在才算已安装；下架和链接缺失归入未安装。
    const deployment = skill.deployments.hermes;
    const installed = deployment?.status === 'active' && !deployment.link_missing;
    if (filters.deployment !== 'all' && (filters.deployment === 'installed') !== installed) {
      return false;
    }
    if (filters.update === 'has_update' && !skill.update?.has_update) {
      return false;
    }
    if (filters.update === 'no_update' && skill.update?.has_update) {
      return false;
    }
    return true;
  });
}

/** 单来源管理两件套：Skill 池 + 独立发布队列（自包含状态与发布确认弹窗）。 */
export default function SourceWorkspace({
  source,
  exportTargets,
  targetsError,
  onManageTargets,
  skills,
  loading,
  onRefresh,
  onNotify,
  onClone,
  onDelete,
  onUnpublish,
  onCheckUpdates,
  checkingUpdates,
}: SourceWorkspaceProps) {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [installIds, setInstallIds] = useState<string[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [editingTagsSkill, setEditingTagsSkill] = useState<SkillCard | null>(null);
  const [exportAction, setExportAction] = useState<{ skill: SkillCard; removing?: ExportTargetKey; initialTarget?: ExportTargetKey } | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const allTags = useMemo(() => {
    const tags = new Set<string>();
    for (const skill of skills) {
      for (const tag of skill.tags) {
        tags.add(tag);
      }
    }
    return [...tags].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  }, [skills]);

  const filteredSkills = useMemo(() => applyFilters(skills, filters), [skills, filters]);

  function handleToggleQueueTarget(skillId: string) { setInstallIds([skillId]); }
  function handleAddCollection(collection: SkillCollection) { setInstallIds(collection.members.map(s => s.id)); }

  async function performSaveTags(tags: string[]) {
    if (!editingTagsSkill) {
      return;
    }
    const skill = editingTagsSkill;
    setActionBusy(true);
    setActionError('');
    try {
      await updateSkillTags(skill.id, tags);
      setEditingTagsSkill(null);
      onNotify({
        kind: 'ok',
        text: `已保存「${skill.name}」的标签（${tags.length} 个）`,
      });
      await onRefresh();
    } catch (err) {
      setActionError(
        err instanceof ApiClientError || err instanceof Error ? err.message : '保存失败'
      );
    } finally {
      setActionBusy(false);
    }
  }

  async function performExport(target: ExportTargetKey) {
    if (!exportAction) return;
    setActionBusy(true);
    setActionError('');
    try {
      if (exportAction.removing) await deleteExport(exportAction.skill.id, target);
      else await exportSkill(exportAction.skill.id, target);
      onNotify({ kind: 'ok', text: exportAction.removing ? '已清除导出记录，本地文件保留' : `已导出「${exportAction.skill.name}」，台账已记录` });
      setExportAction(null);
      await onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '导出操作失败');
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <div
      data-source={source}
      className="grid min-h-0 flex-1 grid-cols-1 gap-4 "
    >
      {/* 左：Skill 池 */}
      <section className="flex min-h-0 flex-col gap-3 overflow-hidden">
        <div className="flex shrink-0 flex-col gap-3">
        <SkillFilters
          value={filters}
          allTags={allTags}
          onChange={setFilters}
          showUpdateFilter={source === 'github'}
        />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {loading ? (
          <p className="p-6 text-center text-sm text-slate-400">加载中…</p>
        ) : (
          <SkillPool
            skills={filteredSkills}
            allSkills={skills}
            onAddCollection={handleAddCollection}
            onInstallSelection={setInstallIds}
            onCheckCollection={(collection) => void onCheckUpdates?.(collection.members.map(s => s.id))}
            checkingUpdates={checkingUpdates}
            exportTargets={exportTargets}
            queue={[]}
            selectedIds={source === 'github' ? selectedIds : undefined}
            onSelect={source === 'github' ? (id, selected) => setSelectedIds(prev => selected ? [...new Set([...prev,id])] : prev.filter(item => item !== id)) : undefined}
            onToggleQueueTarget={handleToggleQueueTarget}
            onClone={onClone}
            onDelete={onDelete}
            onUnpublish={onUnpublish}
            onExport={(skill, initialTarget) => { setActionError(''); setExportAction({ skill, initialTarget }); }}
            onDeleteExport={(skill, removing) => { setActionError(''); setExportAction({ skill, removing }); }}
            onEditTags={(skill) => {
              setActionError('');
              setEditingTagsSkill(skill);
            }}
          />
        )}
        </div>
      </section>

      {editingTagsSkill ? (
        <EditSkillTagsDialog
          skill={editingTagsSkill}
          allTags={allTags}
          busy={actionBusy}
          error={actionError}
          onSave={(tags) => void performSaveTags(tags)}
          onClose={() => setEditingTagsSkill(null)}
        />
      ) : null}

      {exportAction ? <ExportDialog targets={exportTargets} targetsError={targetsError} onManageTargets={() => { setExportAction(null); onManageTargets(); }} skill={exportAction.skill} removing={exportAction.removing} initialTarget={exportAction.initialTarget} busy={actionBusy} error={actionError} onConfirm={(target) => void performExport(target)} onClose={() => setExportAction(null)} /> : null}

      {installIds && <InstallDialog input={{skill_ids: installIds}} onClose={() => setInstallIds(null)} onRefresh={onRefresh} />}
    </div>
  );
}
