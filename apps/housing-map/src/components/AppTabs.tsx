'use client';

export type AppTab = 'map' | 'dashboard' | 'market' | 'auction' | 'review' | 'maintenance';

/** 顶层页签。收录审核与小区数据维护各自独立，与地图查看同级。 */
const tabs: { key: AppTab; label: string }[] = [
  { key: 'map', label: '地图查看' },
  { key: 'dashboard', label: '数据看板' },
  { key: 'market', label: '市场行情' },
  { key: 'auction', label: '法拍数据' },
  { key: 'review', label: '小区收录审核' },
  { key: 'maintenance', label: '小区数据维护' },
];

export default function AppTabs({ active, onChange }: { active: AppTab; onChange: (tab: AppTab) => void }) {
  return <div className="tab-nav">
    {tabs.map(tab => <button key={tab.key} className={`tab-btn ${active === tab.key ? 'active' : ''}`}
      onClick={() => onChange(tab.key)}>{tab.label}</button>)}
  </div>;
}
