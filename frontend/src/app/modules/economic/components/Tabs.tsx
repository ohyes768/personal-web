/**
 * Tab组件
 */
'use client';

interface Tab {
  id: string;
  label: string;
  description: string;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

export function Tabs({ tabs, activeTab, onTabChange }: TabsProps) {
  return (
    <div className="w-full mb-8">
      <div className="flex flex-wrap gap-2 border-b border-gray-800 pb-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`px-6 py-3 rounded-t-lg transition-all duration-200 font-medium text-sm md:text-base ${
              activeTab === tab.id
                ? 'bg-blue-600 text-white shadow-lg'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab描述 */}
      <div className="mt-4">
        {tabs.map((tab) => (
          activeTab === tab.id && (
            <p key={tab.id} className="text-gray-400 text-sm">
              {tab.description}
            </p>
          )
        ))}
      </div>
    </div>
  );
}