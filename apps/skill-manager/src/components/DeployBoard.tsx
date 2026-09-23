'use client';

import { useMemo, useState } from 'react';
import type { TargetKey } from '@/lib/queue';
import type { SkillCard } from '@/lib/types';

const AGENTS: { key: TargetKey; label: string }[] = [
  { key: 'openclaw', label: 'OpenClaw' },
  { key: 'hermes', label: 'Hermes' },
];

const SOURCE_LABEL: Record<SkillCard['source'], string> = {
  local: '自研',
  github: 'GitHub',
};

const SOURCE_BADGE: Record<SkillCard['source'], string> = {
  local: 'bg-violet-50 text-violet-700',
  github: 'bg-sky-50 text-sky-700',
};

const SEG_BUTTON =
  'rounded px-3 py-1 text-sm transition-colors data-[active=true]:bg-white data-[active=true]:font-medium data-[active=true]:text-slate-800 data-[active=true]:shadow-sm text-slate-500 hover:text-slate-700';

interface DeployBoardProps {
  skills: SkillCard[];
  /** 当前 agent 由 page 层从 URL 派生（?view=board&agent=…），受控传入 */
  agent: TargetKey;
  onAgentChange: (agent: TargetKey) => void;
  onUnpublish: (skillId: string, skillName: string, target: TargetKey) => void;
}

function formatPublishedAt(value: string): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('zh-CN', { hour12: false });
}

/** 部署看板：agent 维度纯账本视图（回滚已移除，见任务 PRD R5）。 */
export default function DeployBoard({
  skills,
  agent,
  onAgentChange,
  onUnpublish,
}: DeployBoardProps) {
  const [query, setQuery] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | SkillCard['source']>('all');
  const [sort, setSort] = useState<'time' | 'name'>('time');

  const items = useMemo(() => {
    const deployed = skills
      .map((skill) => ({ skill, deployment: skill.deployments[agent] }))
      .filter(({ deployment }) => deployment?.status === 'active');
    const q = query.trim().toLowerCase();
    const filtered = deployed.filter(({ skill }) => {
      if (sourceFilter !== 'all' && skill.source !== sourceFilter) {
        return false;
      }
      if (q && !`${skill.name} ${skill.id}`.toLowerCase().includes(q)) {
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

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {/* 二级 segmented：agent 类型 */}
        <div className="flex gap-0.5 rounded-md border border-slate-200 bg-slate-50 p-0.5">
          {AGENTS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              data-active={agent === key}
              onClick={() => onAgentChange(key)}
              className={SEG_BUTTON}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="按名称 / ID 搜索"
          className="min-w-40 flex-1 rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
        />
        <select
          value={sourceFilter}
          onChange={(event) =>
            setSourceFilter(event.target.value as 'all' | SkillCard['source'])
          }
          className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
          aria-label="来源筛选"
        >
          <option value="all">来源：全部</option>
          <option value="local">来源：自研</option>
          <option value="github">来源：GitHub</option>
        </select>
        <select
          value={sort}
          onChange={(event) => setSort(event.target.value as 'time' | 'name')}
          className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
          aria-label="排序方式"
        >
          <option value="time">排序：发布时间 ↓</option>
          <option value="name">排序：名称</option>
        </select>
        <span className="text-xs font-semibold tracking-wide text-slate-400">
          {agent === 'openclaw' ? 'OpenClaw' : 'Hermes'} · {items.length} 个已部署
        </span>
      </div>

      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          {totalCount === 0
            ? `${agent === 'openclaw' ? 'OpenClaw' : 'Hermes'} 上暂无已部署的 Skill`
            : '没有符合筛选条件的部署记录'}
        </p>
      ) : (
        <ul className="grid min-h-0 flex-1 grid-cols-1 content-start items-stretch gap-2.5 overflow-y-auto pr-1 md:grid-cols-2 lg:grid-cols-3">
          {items.map(({ skill, deployment }) => (
            <li
              key={skill.id}
              className="flex flex-col rounded-lg border border-slate-200 bg-white p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate font-medium text-slate-800">{skill.name}</h3>
                  <p className="truncate text-xs text-slate-400">{skill.id}</p>
                </div>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${SOURCE_BADGE[skill.source]}`}
                >
                  {SOURCE_LABEL[skill.source]}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                {deployment.revision ? (
                  <span className="font-mono">{deployment.revision.slice(0, 7)}</span>
                ) : null}
                {deployment.published_at ? (
                  <span>· {formatPublishedAt(deployment.published_at)}</span>
                ) : null}
                {deployment.link_missing ? (
                  <span
                    className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700"
                    title="账本记录已发布，但目标目录的链接已不存在（可能被手动删除）"
                  >
                    链接缺失
                  </span>
                ) : null}
              </div>
              <div className="mt-auto flex justify-end border-t border-slate-100 pt-2">
                <button
                  type="button"
                  onClick={() => onUnpublish(skill.id, skill.name, agent)}
                  className="rounded border border-rose-200 px-2.5 py-1 text-xs text-rose-600 hover:bg-rose-50"
                >
                  下架
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
