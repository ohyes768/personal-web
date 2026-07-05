import type { PostInfo } from '@/lib/types';
import { formatTime } from '@/lib/hooks';

interface Props {
  post: PostInfo;
  onSelect: (post: PostInfo) => void;
}

export default function PostCard({ post, onSelect }: Props) {
  return (
    <article
      onClick={() => onSelect(post)}
      className="group bg-paper-card border border-rule rounded-[10px] p-5 cursor-pointer transition-all duration-200 hover:-translate-y-px hover:border-ink-soft hover:shadow-[0_2px_4px_rgba(43,42,40,0.05),0_6px_16px_rgba(43,42,40,0.06)]"
    >
      {/* 标题 */}
      <h3 className="font-serif-cn text-[19px] font-semibold text-ink-strong leading-snug mb-2 line-clamp-2">
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
