"use client";

/** 标签药丸：列表行内、筛选栏、编辑弹窗共用。

 * 列表行内是只读展示（active 高亮只表示该标签正在被筛选栏选中，点击筛选用筛选栏）；
 * 筛选栏与弹窗里传 onClick 时才是按钮（aria-pressed 标选中态）。
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
      <span className={`tag-pill static${active ? " active" : ""}`} title={title}>
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
      title={title}
    >
      {tag}
    </button>
  );
}
