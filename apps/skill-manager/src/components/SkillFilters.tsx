'use client';

export interface FilterState {
  query: string;
  tags: string[];
  deployment: 'all' | 'published' | 'unpublished';
  update: 'all' | 'has_update' | 'no_update';
}

export const DEFAULT_FILTERS: FilterState = {
  query: '',
  tags: [],
  deployment: 'all',
  update: 'all',
};

interface SkillFiltersProps {
  value: FilterState;
  allTags: string[];
  onChange: (next: FilterState) => void;
  /** 更新检查只对 GitHub 来源有意义（自研走 symlink，源目录改了自动生效）。 */
  showUpdateFilter?: boolean;
}

const SELECT_CLASS =
  'rounded border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none';

/** 左栏筛选器：名称、标签多选、部署状态、更新状态（来源由子 tab 承担）。 */
export default function SkillFilters({
  value,
  allTags,
  onChange,
  showUpdateFilter = false,
}: SkillFiltersProps) {
  function toggleTag(tag: string) {
    const tags = value.tags.includes(tag)
      ? value.tags.filter((t) => t !== tag)
      : [...value.tags, tag];
    onChange({ ...value, tags });
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={value.query}
          onChange={(event) => onChange({ ...value, query: event.target.value })}
          placeholder="按名称 / ID / 简介搜索"
          className="min-w-40 flex-1 rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
        />
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
        {showUpdateFilter ? (
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
        ) : null}
      </div>
      {allTags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-2">
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
