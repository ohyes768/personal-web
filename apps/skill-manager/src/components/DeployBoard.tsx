'use client';

import { useInstallTargets, installTargetLabel } from '@/lib/installTargets';
import { useMemo, useState } from 'react';
import type { TargetKey } from '@/lib/queue';
import type { SkillCard } from '@/lib/types';
import { formatPublishedAt, shortRepo } from '@/lib/format';
import { groupCollections } from '@/lib/collections';
import { UnlinkIcon } from '@/components/icons';
import { cardClass, emptyStateClass, ghostDangerButton, toolbarInput, toolbarSelect } from '@/lib/ui';

const SOURCE_LABEL: Record<SkillCard['source'], string> = {
  local: '自研',
  github: 'GitHub',
};

const SOURCE_BADGE: Record<SkillCard['source'], string> = {
  local: 'bg-violet-50 text-violet-700',
  github: 'bg-sky-50 text-sky-700',
};

interface DeployBoardProps {
  skills: SkillCard[];
  /** 当前 agent 由 page 层从 URL 派生（?view=board&agent=…），受控传入 */
  agent: TargetKey;
  onAgentChange: (agent: TargetKey) => void;
  onUnpublishCollection: (name: string, members: SkillCard[], target: TargetKey) => void;
  onUnpublish: (skillId: string, skillName: string, target: TargetKey) => void;
}

/** 部署看板：agent 维度纯账本视图（回滚已移除，见任务 PRD R5）。 */
export default function DeployBoard({
  skills,
  agent,
  onUnpublish,
  onUnpublishCollection,
}: DeployBoardProps) {
  const [query, setQuery] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | SkillCard['source']>('all');
  const [sort, setSort] = useState<'time' | 'name'>('time');
  const {targets} = useInstallTargets();
  const agentLabel = installTargetLabel(targets, agent);
  const unavailable = !targets.find(t => t.id === agent)?.available;

  const items = useMemo(() => {
    const deployed = skills
      .map((skill) => ({ skill, deployment: skill.deployments[agent] }))
      .filter(({ deployment }) => deployment?.status === 'active');
    const q = query.trim().toLowerCase();
    const filtered = deployed.filter(({ skill }) => {
      if (sourceFilter !== 'all' && skill.source !== sourceFilter) {
        return false;
      }
      if (q && !`${skill.name} ${skill.id} ${skill.summary} ${skill.repository ?? ''}`.toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
    return filtered.sort(({ skill: a, deployment: da }, { skill: b, deployment: db }) =>
      sort === 'name'
        ? a.name.localeCompare(b.name, 'zh-CN')
        : db.published_at.localeCompare(da.published_at)
    );
  }, [skills, agent, query, sourceFilter, sort]);

  const totalCount = skills.filter(
    (skill) => skill.deployments[agent]?.status === 'active'
  ).length;

  const groups = groupCollections(skills.filter(s => s.deployments[agent]?.status === 'active'), items.map(i => i.skill));
  const latestPublishedAt = (members: SkillCard[]) => members.reduce((latest, skill) =>
    skill.deployments[agent].published_at > latest ? skill.deployments[agent].published_at : latest, '');
  groups.sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name, 'zh-CN') :
    latestPublishedAt(b.members).localeCompare(latestPublishedAt(a.members)));
  function renderMember(skill: SkillCard) {
    const deployment = skill.deployments[agent];

    // 副标题逻辑与管理看板一致：GitHub 显示 owner/repo，id 与 name 重复则不显示
    const subtitle =
      skill.source === 'github' && skill.repository
        ? shortRepo(skill.repository)
        : skill.id !== skill.name
          ? skill.id
          : '';
    return (
      <li
        key={skill.id}
        className={`flex flex-col ${cardClass}`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate font-medium text-slate-800">{skill.name}</h3>
            {subtitle ? (
              <p className="truncate text-xs text-slate-500" title={subtitle}>
                {subtitle}
              </p>
            ) : null}
          </div>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${SOURCE_BADGE[skill.source]}`}
          >
            {SOURCE_LABEL[skill.source]}
          </span>
        </div>
        {skill.summary ? (
          <p className="mt-1.5 line-clamp-2 text-sm text-slate-600">{skill.summary}</p>
        ) : null}
        {skill.tags.length > 0 ? (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {skill.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}

        {/* 本 agent 的安装信息 */}
        <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="w-16 shrink-0 text-slate-500">{agentLabel}</span>
            <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">
              已发布
              {deployment.revision ? ` · ${deployment.revision.slice(0, 7)}` : ''}
            </span>
            {deployment.link_missing ? (
              <span
                className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700"
                title="账本记录已发布，但目标目录的链接已不存在（可能被手动删除）"
              >
                链接缺失
              </span>
            ) : null}
          </div>
          {deployment.published_at ? (
            <div className="flex items-center gap-2">
              <span className="w-16 shrink-0 text-slate-500">安装时间</span>
              <span className="text-slate-500">
                {formatPublishedAt(deployment.published_at)}
              </span>
            </div>
          ) : null}
        </div>

        <div className="mt-auto flex justify-end border-t border-slate-100 pt-2">
          <button
            type="button"
            aria-label="下架"
            disabled={unavailable}
            data-tip={`从 ${agentLabel} 下架`}
            onClick={() => onUnpublish(skill.id, skill.name, agent)}
            className="icon-btn tip-right icon-btn-danger rounded-md border border-rose-200"
          >
            <UnlinkIcon />
          </button>
        </div>
      </li>
    );

  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{agentLabel} 安装</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="按仓库 / 名称 / ID 搜索"
          className={`min-w-40 flex-1 ${toolbarInput}`}
        />
        <select
          value={sourceFilter}
          onChange={(event) =>
            setSourceFilter(event.target.value as 'all' | SkillCard['source'])
          }
          className={toolbarSelect}
          aria-label="来源筛选"
        >
          <option value="all">来源：全部</option>
          <option value="local">来源：自研</option>
          <option value="github">来源：GitHub</option>
        </select>
        <select
          value={sort}
          onChange={(event) => setSort(event.target.value as 'time' | 'name')}
          className={toolbarSelect}
          aria-label="排序方式"
        >
          <option value="time">排序：发布时间 ↓</option>
          <option value="name">排序：名称</option>
        </select>
        <span className="text-xs font-semibold tracking-wide text-slate-600">
          {agentLabel} · {items.length} 个已部署
        </span>
      </div>

      {items.length === 0 ? (
        <p className={`${emptyStateClass} p-6 text-sm text-slate-600`}>
          {totalCount === 0
            ? `${agentLabel} 上暂无已部署的 Skill`
            : '没有符合筛选条件的部署记录'}
        </p>
      ) : (
        <ul className="grid min-h-0 flex-1 grid-cols-1 content-start items-stretch gap-2.5 overflow-y-auto pr-1 md:grid-cols-2 lg:grid-cols-3">
          {groups.map(group => group.members[0].source === 'local' ? renderMember(group.members[0]) : (
            <li key={group.key} className={cardClass}>
              <h3 className="font-semibold text-slate-800">{group.name}</h3>
              <p className="break-all text-xs text-slate-500">{group.repository ?? '仓库地址异常'}</p>
              <p className="mt-2 text-sm text-slate-600">{agentLabel} · 已发布 {group.members.filter(s => !s.deployments[agent].link_missing).length}/{group.members.length}
                {group.members.some(s => s.deployments[agent].link_missing) ? ' · 有链接缺失' : ''}
                {group.visibleMembers.length !== group.members.length ? ` · 匹配 ${group.visibleMembers.length} 项` : ''}
              </p>
              <button type="button" disabled={unavailable}
                      onClick={() => onUnpublishCollection(group.name, group.members, agent)}
                className={`mt-3 ${ghostDangerButton}`}>
                从 {agentLabel} 全部下架（{group.members.length} 项）
              </button>
              <details className="mt-3 border-t border-slate-100 pt-2">
                <summary className="cursor-pointer text-sm text-slate-600">部署详情（{group.visibleMembers.length}）</summary>
                <ul className="mt-2 space-y-2">{group.visibleMembers.map(renderMember)}</ul>
              </details>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
