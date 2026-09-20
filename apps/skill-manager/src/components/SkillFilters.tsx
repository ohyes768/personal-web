'use client';

import type { SkillSource } from '@/lib/types';

export interface FilterState {
  query: string;
  source: 'all' | SkillSource;
  tags: string[];
  deployment: 'all' | 'published' | 'unpublished';
  update: 'all' | 'has_update' | 'no_update';
  status: 'all' | 'active' | 'deprecated';
}

export const DEFAULT_FILTERS: FilterState = {
  query: '',
  source: 'all',
  tags: [],
  deployment: 'all',
  update: 'all',
  status: 'all',
};

interface SkillFiltersProps {
  value: FilterState;
  allTags: string[];
  onChange: (next: FilterState) => void;
}

const SELECT_CLASS =
  'rounded border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none';

/** 左栏筛选器（design 4.1）：名称、来源、标签多选、部署状态、更新状态、启用状态。 */
export default function SkillFilters({ value, allTags, onChange }: SkillFiltersProps) {
  function toggleTag(tag: string) {
    const tags = value.tags.includes(tag)
      ? value.tags.filter((t) => t !== tag)
      : [...value.tags, tag];
    onChange({ ...value, tags });
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-3">
      <input
        type="search"
        value={value.query}
        onChange={(event) => onChange({ ...value, query: event.target.value })}
        placeholder="按名称 / ID / 简介搜索"
        className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
      />
      <div className="flex flex-wrap gap-2">
        <select
          value={value.source}
          onChange={(event) =>
            onChange({ ...value, source: event.target.value as FilterState['source'] })
          }
          className={SELECT_CLASS}
          aria-label="来源筛选"
        >
          <option value="all">来源：全部</option>
          <option value="local">自研</option>
          <option value="github">GitHub</option>
        </select>
        <select
          value={value.deployment}
          onChange={(event) =>
            onChange({
              ...value,
              deployment: event.target.value as FilterState['deployment'],
            })
          }
          className={SELECT_CLASS}
          aria-label="部署状态筛选"
        >
          <option value="all">部署：全部</option>
          <option value="published">已发布（任一目标）</option>
          <option value="unpublished">未发布</option>
        </select>
        <select
          value={value.update}
          onChange={(event) =>
            onChange({ ...value, update: event.target.value as FilterState['update'] })
          }
          className={SELECT_CLASS}
          aria-label="更新状态筛选"
        >
          <option value="all">更新：全部</option>
          <option value="has_update">有待更新</option>
          <option value="no_update">无更新</option>
        </select>
        <select
          value={value.status}
          onChange={(event) =>
            onChange({ ...value, status: event.target.value as FilterState['status'] })
          }
          className={SELECT_CLASS}
          aria-label="启用状态筛选"
        >
          <option value="all">状态：全部</option>
          <option value="active">启用</option>
          <option value="deprecated">已弃用</option>
        </select>
      </div>
      {allTags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {allTags.map((tag) => {
            const active = value.tags.includes(tag);
            return (
              <button
                key={tag}
                type="button"
                onClick={() => toggleTag(tag)}
                className={`rounded-full px-2.5 py-0.5 text-xs ${
                  active
                    ? 'bg-sky-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {tag}
              </button>
            );
          })}
          {value.tags.length > 0 ? (
            <button
              type="button"
              onClick={() => onChange({ ...value, tags: [] })}
              className="text-xs text-slate-400 underline hover:text-slate-600"
            >
              清除标签
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
