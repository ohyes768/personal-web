"use client";

import { TagBadge } from "@/components/TagBadge";

/** 标签筛选栏：全库标签药丸排，多选 AND；选中非空时给「清除标签」。 */

export function TagFilterBar({
  allTags,
  selected,
  onChange,
}: {
  allTags: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  if (allTags.length === 0) return null;
  return (
    <div className="tag-filter-bar">
      <span className="small muted">按标签筛选（同时满足）</span>
      <div className="tag-row">
        {allTags.map((tag) => (
          <TagBadge
            key={tag}
            tag={tag}
            active={selected.includes(tag)}
            onClick={() =>
              onChange(
                selected.includes(tag)
                  ? selected.filter((item) => item !== tag)
                  : [...selected, tag],
              )
            }
          />
        ))}
      </div>
      {selected.length > 0 ? (
        <button type="button" className="link-btn" onClick={() => onChange([])}>
          清除标签
        </button>
      ) : null}
    </div>
  );
}
