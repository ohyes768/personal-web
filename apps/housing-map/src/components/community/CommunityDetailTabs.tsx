'use client';
import { useState, type ReactNode } from 'react';
import CommunityAuctionHistory from './CommunityAuctionHistory';

export default function CommunityDetailTabs({ communityId, auctionCount, children }: {
  communityId: string; auctionCount?: number; children: ReactNode;
}) {
  const [tab, setTab] = useState<'overview' | 'auction'>('overview');
  return <>
    <div className="community-detail-tabs" role="tablist" aria-label="小区详情">
      <button id={`overview-tab-${communityId}`} role="tab" aria-selected={tab === 'overview'} aria-controls={`overview-panel-${communityId}`} onClick={() => setTab('overview')}>小区概况</button>
      <button id={`auction-tab-${communityId}`} role="tab" aria-selected={tab === 'auction'} aria-controls={`auction-panel-${communityId}`} onClick={() => setTab('auction')}>法拍成交{auctionCount ? <span>{auctionCount}</span> : null}</button>
    </div>
    {tab === 'overview' ? <div role="tabpanel" id={`overview-panel-${communityId}`} aria-labelledby={`overview-tab-${communityId}`}>{children}</div> : <div role="tabpanel" id={`auction-panel-${communityId}`} aria-labelledby={`auction-tab-${communityId}`}><CommunityAuctionHistory communityId={communityId} /></div>}
  </>;
}
