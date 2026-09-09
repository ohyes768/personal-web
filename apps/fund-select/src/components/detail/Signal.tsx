/**
 * 信号灯：5 段灯条（带数据 segment）
 * - segment=0 全暗；1-4 对应亮起段数
 * - 缺失数据用 0 段，全暗
 * - 紧凑尺寸 + 灯间细缝
 */
import { SIGNAL_PALETTE, type Segment } from './score';

interface SignalProps {
  segment: Segment;
  /** 单段宽度（px），默认 8 */
  size?: number;
  /** 显示缺失时的灰底（默认 true） */
  showEmptyTrack?: boolean;
  /** a11y 标签 */
  label?: string;
}

export function Signal({
  segment,
  size = 8,
  showEmptyTrack = true,
  label,
}: SignalProps) {
  const cells = Array.from({ length: 5 }, (_, i) => i);
  return (
    <span
      className="inline-flex items-center gap-[3px] align-middle"
      role="img"
      aria-label={label ?? `${segment} / 5`}
    >
      {cells.map(i => {
        const lit = i < segment;
        return (
          <span
            key={i}
            className="inline-block rounded-[1.5px]"
            style={{
              width: `${size}px`,
              height: `${size * 1.4}px`,
              background: lit
                ? SIGNAL_PALETTE[Math.min(segment, 4)]
                : showEmptyTrack
                  ? 'var(--color-paper-deep)'
                  : 'transparent',
              boxShadow: lit
                ? `inset 0 0 0 1px rgb(0 0 0 / 0.06)`
                : 'none',
            }}
          />
        );
      })}
    </span>
  );
}
