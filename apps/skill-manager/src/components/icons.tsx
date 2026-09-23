/**
 * 管理台手绘线性图标集（24 viewBox，stroke 1.8，随 currentColor 着色）。
 *
 * OpenClaw = 小龙虾（claw 螯），Hermes = 双翼 + 闪电（神使速度），
 * 其余为操作语义：加入队列 / Clone / 下架（断链）/ 删除。
 */

const STROKE_PROPS = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
};

export function CrayfishIcon() {
  return (
    <svg {...STROKE_PROPS}>
      {/* 双螯 */}
      <circle cx="6" cy="5.8" r="2.5" />
      <circle cx="18" cy="5.8" r="2.5" />
      {/* 螯-身连接 */}
      <path d="M8.1 7.3 10 9.6M15.9 7.3 14 9.6" />
      {/* 身体 */}
      <ellipse cx="12" cy="13.4" rx="3.9" ry="4.6" />
      {/* 触须 */}
      <path d="M10.6 8.9c-.3-2.2.4-3.8 1.4-5.1M13.4 8.9c.3-2.2-.4-3.8-1.4-5.1" />
      {/* 尾扇 */}
      <path d="M9.4 17.7 8.4 21.2M14.6 17.7l1 3.5M12 18.1v3.4" />
    </svg>
  );
}

export function HermesIcon() {
  return (
    <svg {...STROKE_PROPS}>
      {/* 双翼 */}
      <path d="M11.3 13.6c0-4.7-2.6-8.4-7.5-9.8 1.6 4.6 4.4 7.7 7.5 8.8" />
      <path d="M12.7 13.6c0-4.7 2.6-8.4 7.5-9.8-1.6 4.6-4.4 7.7-7.5 8.8" />
      {/* 闪电 */}
      <path d="M13 9.5 9.8 14.6h2.5L11.2 20l4.3-5.8h-2.5l1.5-4.7z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function PlusIcon() {
  return (
    <svg {...STROKE_PROPS}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function DownloadIcon() {
  return (
    <svg {...STROKE_PROPS}>
      <path d="M12 3v11" />
      <path d="m7.5 9.5 4.5 4.5 4.5-4.5" />
      <path d="M4.5 20h15" />
    </svg>
  );
}

export function UnlinkIcon() {
  return (
    <svg {...STROKE_PROPS}>
      <path d="M9 15 15 9" />
      <path d="M12.5 6.5 14 5a3.9 3.9 0 0 1 5.5 5.5L18 12" />
      <path d="M11.5 17.5 10 19a3.9 3.9 0 0 1-5.5-5.5L6 12" />
    </svg>
  );
}

export function TrashIcon() {
  return (
    <svg {...STROKE_PROPS}>
      <path d="M4 7h16" />
      <path d="M9.5 7V5.2c0-.7.5-1.2 1.2-1.2h2.6c.7 0 1.2.5 1.2 1.2V7" />
      <path d="m6 7 .9 12.2c.1 1 .9 1.8 1.9 1.8h6.4c1 0 1.8-.8 1.9-1.8L18 7" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}
