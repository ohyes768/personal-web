'use client';
import { useState, type ReactNode } from 'react';

export default function CommunityDetailTabs({ communityId, children, boundary }: {
  communityId: string; auctionCount?: number; children: ReactNode; boundary?: ReactNode;
}) {
  const [tab, setTab] = useState<'overview' | 'boundary'>('overview');
  const panel = (name: string) => ({
    role: 'tabpanel' as const,
    id: `${name}-panel-${communityId}`,
    'aria-labelledby': `${name}-tab-${communityId}`,
  });
  return <>
    <div className="community-detail-tabs" role="tablist" aria-label="小区详情">
      <button id={`overview-tab-${communityId}`} role="tab" aria-selected={tab === 'overview'} aria-controls={`overview-panel-${communityId}`} onClick={() => setTab('overview')}>小区概况</button>
      {boundary && <button id={`boundary-tab-${communityId}`} role="tab" aria-selected={tab === 'boundary'} aria-controls={`boundary-panel-${communityId}`} onClick={() => setTab('boundary')}>地块轮廓</button>}
    </div>
    {tab === 'overview' && <div {...panel('overview')}>{children}</div>}
    {tab === 'boundary' && boundary && <div {...panel('boundary')}>{boundary}</div>}
  </>;
}
