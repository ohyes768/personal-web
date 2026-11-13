"use client";

/** 标签药丸：列表页、详情页共用。

 * 可点击时是「按该标签筛选」的按钮（aria-pressed 标选中态，颜色之外还有形状差异）；
 * 不可点击时退化成静态标签。
 */

export function TagBadge({
  tag,
  active = false,
  onClick,
  title,
}: {
  tag: string;
  active?: boolean;
  onClick?: () => void;
  title?: string;
}) {
  if (!onClick) {
    return (
      <span className="tag-pill static" title={title}>
        {tag}
      </span>
    );
  }
  return (
    <button
      type="button"
      className={`tag-pill${active ? " active" : ""}`}
      aria-pressed={active}
      onClick={onClick}
      title={title ?? (active ? "取消这个标签的筛选" : "按这个标签筛选")}
    >
      {tag}
    </button>
  );
}
