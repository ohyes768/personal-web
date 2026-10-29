'use client';

// 新房项目详情面板: 只展示已有可核验的项目资料、位置证据与配套。
//
// 与二手房详情分开渲染: 新房没有可信价格来源, 也没有可比的市场评分,
// 把二手的租售收益、成交套数、评分摆在新房旁边会制造"可比"的错觉。
// 缺字段就明说没有, 不拿二手快照或名称猜测补位。

import type { ReactNode } from 'react';
import type { Community } from '../../lib/types';
import { hasTrustedNewHousePrice, NEARBY_DEFAULT_RADIUS_METERS, newHousePriceText, type PriceMode } from '../../lib/market-map';
import NearbySecondHandList from './NearbySecondHandList';

// 位置来源文案: 只说明证据来自哪里, 不夸大核验程度。
// historical_amap 是历史快照坐标, 不等于本次现场核验, 所以核验状态仍是"待核实"。
const POSITION_SOURCE_LABELS: Record<string, string> = {
  amap: '高德定位',
  manual: '人工确认',
  historical_amap: '历史快照',
};

export interface NewHouseDetailProps {
  community: Community;
  priceMode: PriceMode;
  onClose: () => void;
  // 管理端核对入口: 位置待核实时给一个去核对的位置
  onLocate?: () => void;
  // 周边配套由调用方复用既有 POI 磁贴渲染
  poiContent?: ReactNode;
  // 就近比较: 锚点是当前项目, 候选集合是当前地图可见集合
  nearbyOpen: boolean;
  nearbyCommunities: Community[];
  nearbyConditions: string;
  onToggleNearby: () => void;
  onSelectNearby: (community: Community) => void;
}

export default function NewHouseDetail({
  community,
  priceMode,
  onClose,
  onLocate,
  poiContent,
  nearbyOpen,
  nearbyCommunities,
  nearbyConditions,
  onToggleNearby,
  onSelectNearby,
}: NewHouseDetailProps) {
  const project = community.project ?? null;
  const position = community.position ?? null;
  const hasPosition = position !== null;
  const verified = position?.verified === true;
  const sourceLabel = position?.source
    ? (POSITION_SOURCE_LABELS[position.source] ?? position.source)
    : '暂无位置资料';
  const isHistoricalPosition = position?.source === 'historical_amap';
  const hasBoundary = !!(community.boundary && community.boundary.length > 0 && community.boundary_source !== 'shp');
  const priceText = newHousePriceText(community, priceMode);

  const facts: { label: string; value: string }[] = [
    { label: '销售状态', value: project?.sale_status || '暂无' },
    { label: '项目价格', value: priceText },
    { label: '位置来源', value: sourceLabel },
    { label: '核验状态', value: !hasPosition ? '暂无位置资料' : (verified ? '位置已核验' : '位置待核实') },
  ];

  const details: { label: string; value: string }[] = [
    { label: '项目名称', value: project?.project_name || '暂无' },
    { label: '项目编号', value: project?.project_id || '暂无' },
    { label: '项目所在地', value: position?.address || '暂无' },
    { label: '项目范围', value: hasBoundary ? `已有地块轮廓（${community.boundary_source}）` : '暂无项目范围' },
  ];

  return (
    <div className="community-popup open animate-fade-in">
      <div className="popup-header">
        <div>
          <span className="popup-title">{community.community_name}</span>
          <span className="popup-subdistrict">{community.subdistrict}</span>
        </div>
        <div className="popup-score">
          <span className="nh-badge">新</span>
          <span className="score-label">新房项目</span>
        </div>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <p className="auction-meta">
        新房项目按项目证据展示，不与二手房价格口径混用。
        {project?.captured_at && <> 项目身份采集于 {project.captured_at}。</>}
      </p>

      <div className="popup-price-row nh-fact-grid">
        {facts.map(fact => (
          <div className="stat-cell" key={fact.label}>
            <div className="stat-label">{fact.label}</div>
            <div className="stat-value nh-fact-value">{fact.value}</div>
          </div>
        ))}
      </div>

      {!hasTrustedNewHousePrice(community) && (
        <p className="nh-note">暂无可靠项目价格：备案价/参考均价等明确口径来源缺失，此处不借用二手房价格。</p>
      )}

      <dl className="nh-detail-list">
        {details.map(item => (
          <div className="nh-detail-row" key={item.label}>
            <dt className="nh-detail-label">{item.label}</dt>
            <dd className="nh-detail-value">{item.value}</dd>
          </div>
        ))}
      </dl>

      {!verified && (
        <p className="auction-meta" role="status">
          {hasPosition
            ? '该项目位置尚未核验，地图上的项目点为空心标记；售楼处坐标不能代表项目所在地。'
            : '该项目暂无位置资料，地图上不会画出项目点；售楼处坐标不能代表项目所在地。'}
        </p>
      )}
      {isHistoricalPosition && (
        <p className="nh-note">位置来源是历史快照坐标，不代表本次重新核验过。</p>
      )}
      {!verified && onLocate && (
        <button className="btn btn-secondary nh-locate-btn" onClick={onLocate}>去核对定位</button>
      )}

      {project?.identity_url && (
        <p className="auction-meta">
          身份来源：
          <a href={project.identity_url} target="_blank" rel="noopener noreferrer">查看项目来源 ↗</a>
        </p>
      )}

      {/* 就近比较: 新房与周边二手分开列, 不混算溢价 */}
      <div className="nh-nearby-section">
        <div className="nh-section-head">
          <span className="panel-title">看附近二手房</span>
          <button className="btn btn-secondary nh-nearby-toggle" onClick={onToggleNearby}>
            {nearbyOpen ? '收起附近二手房' : '看附近二手房'}
          </button>
        </div>
        {nearbyOpen ? (
          <NearbySecondHandList
            anchor={community}
            communities={nearbyCommunities}
            priceMode={priceMode}
            conditions={nearbyConditions}
            onSelect={onSelectNearby}
          />
        ) : (
          <p className="nh-note">{`按项目点 ${NEARBY_DEFAULT_RADIUS_METERS / 1000} 公里直线距离列出同一筛选条件下的二手房，用于比较位置与价格口径。`}</p>
        )}
      </div>

      {poiContent}
    </div>
  );
}
