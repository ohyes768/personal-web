/**
 * Tabs 组件
 * 通用 Tab 切换组件
 */

export interface Tab {
  id: string;
  label: string;
}

export interface TabsProps {
  tabs: readonly Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onTabChange, className = '' }: TabsProps) {
  return (
    <div className={`flex gap-1 ${className}`}>
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`px-6 py-2 transition-colors ${
            index === 0 && tabs.length > 1
              ? 'rounded-l-lg'
              : index === tabs.length - 1
              ? 'rounded-r-lg'
              : ''
          } ${
            activeTab === tab.id
              ? 'bg-blue-600 hover:bg-blue-700'
              : 'bg-gray-700 hover:bg-gray-600'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}