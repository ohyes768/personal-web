'use client';
import { useState, type ReactNode } from 'react';
import CommunityRentalReference from './CommunityRentalReference';

export default function CommunityDetailTabs({ communityId, children, boundary }: {
  communityId: string; auctionCount?: number; children: ReactNode; boundary?: ReactNode;
}) {
  const [tab, setTab] = useState<'overview' | 'rental' | 'boundary'>('overview');
  const panel = (name: string) => ({
    role: 'tabpanel' as const,
    id: `${name}-panel-${communityId}`,
    'aria-labelledby': `${name}-tab-${communityId}`,
  });
  return <>
    <div className="community-detail-tabs" role="tablist" aria-label="小区详情">
      <button id={`overview-tab-${communityId}`} role="tab" aria-selected={tab === 'overview'} aria-controls={`overview-panel-${communityId}`} onClick={() => setTab('overview')}>小区概况</button>
      <button id={`rental-tab-${communityId}`} role="tab" aria-selected={tab === 'rental'} aria-controls={`rental-panel-${communityId}`} onClick={() => setTab('rental')}>租金与收益</button>
      {boundary && <button id={`boundary-tab-${communityId}`} role="tab" aria-selected={tab === 'boundary'} aria-controls={`boundary-panel-${communityId}`} onClick={() => setTab('boundary')}>地块轮廓</button>}
    </div>
    {tab === 'overview' && <div {...panel('overview')}>{children}</div>}
    {tab === 'rental' && <div {...panel('rental')}><CommunityRentalReference communityId={communityId} /></div>}
    {tab === 'boundary' && boundary && <div {...panel('boundary')}>{boundary}</div>}
  </>;
}
