/**
 * Tabs 组件
 * 复制自 packages/shared-ui/src/Tabs.tsx
 * 试点：apps/douyin 拆离 monorepo
 */

export interface Tab {
  id: string;
  label: string;
  badge?: number;
}

export interface TabsProps {
  tabs: readonly Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onTabChange, className = '' }: TabsProps) {
  return (
    <div className={`flex gap-0 border-b border-rule ${className}`}>
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`font-ui relative px-5 py-3 text-[14px] cursor-pointer transition-colors bg-transparent border-0 -mb-px ${
              isActive
                ? 'text-ink-strong font-semibold after:absolute after:bottom-[-1px] after:left-3 after:right-3 after:h-0.5 after:bg-accent'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            {tab.label}
            {tab.badge !== undefined && tab.badge > 0 && (
              <span className="ml-1.5 px-1.5 py-px text-[11px] bg-accent text-paper rounded-full align-middle inline-block leading-tight">
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}