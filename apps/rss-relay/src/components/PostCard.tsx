'use client';
import type { PostInfo } from '@/lib/types';
import { formatTime } from '@/lib/hooks';

interface Props {
  post: PostInfo;
  onSelect: (post: PostInfo) => void;
  onDelete?: (post: PostInfo) => void;
  deleting?: boolean;
}

export default function PostCard({ post, onSelect, onDelete, deleting }: Props) {
  const handleDelete = (e: React.MouseEvent) => {
    // 阻止冒泡，避免触发卡片的 onSelect 打开 Modal
    e.stopPropagation();
    if (!onDelete || deleting) return;
    const ok = window.confirm(`确定删除「${post.title || '这篇文章'}」吗？`);
    if (ok) onDelete(post);
  };

  return (
    <article
      onClick={() => onSelect(post)}
      className="group relative bg-paper-card border border-rule rounded-[10px] p-5 cursor-pointer transition-all duration-200 hover:-translate-y-px hover:border-ink-soft hover:shadow-[0_2px_4px_rgba(43,42,40,0.05),0_6px_16px_rgba(43,42,40,0.06)]"
    >
      {/* 删除按钮（右上角，hover 显示；删除中显示 loading） */}
      {onDelete && (
        <button
          onClick={handleDelete}
          disabled={deleting}
          aria-label="删除文章"
          title={deleting ? '删除中…' : '删除文章'}
          className="absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-[6px] text-ink-muted hover:text-danger hover:bg-danger/[0.08] opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-all font-ui text-[18px] leading-none disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {deleting ? '…' : '×'}
        </button>
      )}

      {/* 标题（pr-8 给右上角删除按钮留位置） */}
      <h3 className="font-serif-cn text-[19px] font-semibold text-ink-strong leading-snug mb-2 line-clamp-2 pr-8">
        {post.title}
      </h3>

      {/* 元信息 */}
      <div className="flex items-center gap-3 font-ui text-[13px] text-ink-muted mb-3">
        {post.source && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-[4px] bg-accent/[0.08] text-accent font-medium">
            {post.source}
          </span>
        )}
        <time className="tnum">{formatTime(post.created_at)}</time>
      </div>

      {/* 摘要 */}
      {post.preview && (
        <p className="text-[15px] text-ink-muted leading-relaxed line-clamp-2">
          {post.preview}
        </p>
      )}
    </article>
  );
}
