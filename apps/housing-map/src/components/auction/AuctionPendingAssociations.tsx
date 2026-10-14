'use client';

export function openAuctionCommunityReview() {
  window.dispatchEvent(new CustomEvent('housing-open-community-review', { detail: { source: 'laipai' } }));
}

export default function AuctionPendingAssociations() {
  return <section className="auction-list-card" aria-label="法拍小区审核入口">
    <h3>未关联小区统一审核</h3>
    <p className="auction-meta">来拍 ya 涉及的未关联小区已纳入待审核小区。按小区核对资料，同一资产的拍卖轮次一并处理。</p>
    <button className="btn btn-secondary" onClick={openAuctionCommunityReview}>前往待审核小区</button>
  </section>;
}
