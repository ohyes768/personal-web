'use client';

// 就近比较: 新房项目点附近的二手房列表。
//
// 只做"位置 + 价格口径"的对照, 不做涨跌/溢价推断 —— 两者口径不同, 混算出来的数字没有意义。
// 列表本体由 market-map 的 nearbySecondHand 计算, 组件只负责呈现与交互。

import type { Community } from '../../lib/types';
import {
  NEARBY_DEFAULT_RADIUS_METERS,
  nearbySecondHand,
  secondHandPriceText,
  type PriceMode,
} from '../../lib/market-map';

export interface NearbySecondHandListProps {
  // 比较锚点: 被点开的新房项目
  anchor: Community;
  // 候选集合: 当前地图可见集合(含未核实房源类型, 由 nearbySecondHand 内部只留二手房)
  communities: Community[];
  priceMode: PriceMode;
  // 当前生效的筛选条件说明, 必须随列表一起显示, 否则用户会把结果当成全量
  conditions: string;
  onSelect: (community: Community) => void;
  radiusMeters?: number;
}

export default function NearbySecondHandList({
  anchor,
  communities,
  priceMode,
  conditions,
  onSelect,
  radiusMeters = NEARBY_DEFAULT_RADIUS_METERS,
}: NearbySecondHandListProps) {
  const items = nearbySecondHand(anchor, communities, { radiusMeters });
  const radiusText = `${radiusMeters / 1000} 公里`;
  const anchorHasPosition = Number.isFinite(anchor.latitude) && Number.isFinite(anchor.longitude);

  return (
    <section aria-label="附近二手房">
      <div className="nh-nearby-head">
        <span className="nh-nearby-title">附近二手房（{items.length}）</span>
        <span className="nh-nearby-radius">{radiusText}直线距离</span>
      </div>
      {/* 限制条件必须写出来: 半径 + 当前筛选, 否则列表看起来像"全部二手房" */}
      <p className="nh-note">
        {`以项目点为中心 ${radiusText}直线距离内、且满足当前筛选条件的二手房（直线距离，不等于步行距离）。当前筛选：${conditions}`}
      </p>

      {!anchorHasPosition ? (
        <p className="nh-note">项目位置尚无有效坐标，无法计算直线距离。</p>
      ) : items.length === 0 ? (
        <p className="nh-note">
          {`附近 ${radiusText}内没有符合条件的二手房。可放宽区域、物业类型或搜索条件后再看。`}
        </p>
      ) : (
        <ul className="nh-nearby-list">
          {items.map(item => {
            const community = item.community;
            const snapshotDate = community.price.snapshot_date || '未知';
            return (
              <li key={community.community_id}>
                <button type="button" className="nh-nearby-item" onClick={() => onSelect(community)}>
                  <span className="nh-nearby-name">
                    {community.community_name}
                    <span className="nh-nearby-meta">
                      {community.subdistrict} · 价格日期 {snapshotDate}
                    </span>
                  </span>
                  <span className="nh-nearby-price">{secondHandPriceText(community, priceMode)}</span>
                  <span className="nh-nearby-distance">{item.distance} 米</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
