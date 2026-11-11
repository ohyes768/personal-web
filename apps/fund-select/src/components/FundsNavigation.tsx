/**
 * 五 Tab 公共导航（债基·雪球三分法 | 股基·雪球三分法 | 债基·市场 | 股基·市场 | 夏普榜单）
 *
 * 从 FundsHeader 提取，供旧四个筛选页（经 FundsHeader）与夏普榜单页复用。
 * 注意：导航只负责页面切换；「刷新来源」（FundsTab / exportKind）仍只有
 * 四个采集 tab——夏普榜单页是只读页面，没有刷新入口，不伪造刷新来源。
 *
 * href 是相对 basePath 的路径（basePath=/funds，Link 自动补前缀）。
 */
'use client';

import Link from 'next/link';

export type FundsNavTab =
  | 'bond'
  | 'stock'
  | 'discovery-bond'
  | 'discovery-stock'
  | 'managers'
  | 'sharpe-board';

const TABS: { key: FundsNavTab; href: string; label: string }[] = [
  { key: 'bond', href: '/bond', label: '债基·雪球三分法' },
  { key: 'stock', href: '/stock', label: '股基·雪球三分法' },
  { key: 'discovery-bond', href: '/discovery-bond', label: '债基·市场' },
  { key: 'discovery-stock', href: '/discovery-stock', label: '股基·市场' },
  { key: 'managers', href: '/managers', label: '经理' },
  { key: 'sharpe-board', href: '/sharpe-board', label: '夏普榜单' },
];

export function FundsNavigation({ active }: { active: FundsNavTab }) {
  return (
    <nav className="flex items-center gap-0.5 text-sm flex-wrap" aria-label="基金页面导航">
      {TABS.map(tab => (
        <Link
          key={tab.key}
          href={tab.href}
          aria-current={active === tab.key ? 'page' : undefined}
          className={`px-2 py-0.5 rounded transition-colors ${
            active === tab.key
              ? 'bg-accent text-white'
              : 'text-ink-muted hover:text-ink-strong'
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
