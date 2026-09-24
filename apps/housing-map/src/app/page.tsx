'use client';

import { useState, useCallback, useEffect, useMemo, useRef, type CSSProperties, type ReactNode } from 'react';
import type { Community, MapPOI, MarketReference, SchoolLevel } from '@/lib/types';
import { getDisplayPrice, getPriceColor, getSchoolLevel, isListingReference, SCHOOL_LEVEL_LABELS, SCHOOL_LEVEL_COLORS } from '@/lib/types';
import { isInBinjiang } from '@/lib/binjiang-boundary';
import BinjiangMap from '@/components/map/BinjiangMap';

// 从 API 获取小区数据
async function fetchCommunities(): Promise<Community[]> {
  try {
    const res = await fetch('/api/map/communities');
    const data = await res.json();
    return data.data || [];
  } catch (error) {
    console.error('Failed to fetch communities:', error);
    return [];
  }
}

async function fetchMarketReference(): Promise<MarketReference> {
  try {
    const res = await fetch('/api/map/market-reference');
    const payload = await res.json();
    if (isListingReference(payload.data)) return payload.data;
    return { available: false, reason: payload.data?.reason ?? 'invalid_response' };
  } catch (error) {
    console.error('Failed to fetch market reference:', error);
    return { available: false, reason: 'request_failed' };
  }
}

// POI 图层配置 (浅色底图配色, 与 BinjiangMap 的 POI_MARKER_COLORS 保持一致)
const POI_CONFIG = {
  subway: { color: '#3B76D2', label: '地铁', icon: '🚇' },
  school: { color: '#6C5CE7', label: '学校', icon: '🏫' },
  hospital: { color: '#D94F7E', label: '医院', icon: '🏥' },
  mall: { color: '#DE8F0E', label: '商场', icon: '🛍️' },
  park: { color: '#2E9E55', label: '公园', icon: '🌳' },
  bus: { color: '#4899BE', label: '公交', icon: '🚌' },
} as const;

type POIType = keyof typeof POI_CONFIG;

// 价格区间 -> 颜色: 见 types.ts getPriceColor (浅色主题共用)

// 弹窗周边配套展示的五类 (公交数据量可忽略, 不列)
const POI_TILE_TYPES: POIType[] = ['subway', 'school', 'hospital', 'mall', 'park'];

// 紧凑数值: 过万显示 X.X万
function fmtCompact(value: number | null): string {
  if (value == null) return '-';
  return value >= 10000 ? `${(value / 10000).toFixed(1)}万` : String(value);
}

// 小区弹窗组件
function CommunityPopup({
  community,
  onClose,
}: {
  community: Community;
  onClose: () => void;
}) {
  const poiGroups = community.pois.reduce((acc, poi) => {
    const type = poi.type as POIType;
    if (!acc[type]) acc[type] = [];
    acc[type].push(poi);
    return acc;
  }, {} as Record<POIType, typeof community.pois>);

  // 各类按距离排序 (取"最近"用)
  const poiSorted: Partial<Record<POIType, typeof community.pois>> = {};
  for (const type of Object.keys(poiGroups) as POIType[]) {
    poiSorted[type] = [...poiGroups[type]].sort((a, b) => a.distance - b.distance);
  }

  const [expandedPOI, setExpandedPOI] = useState<POIType | null>(null);
  // 每张评分卡独立翻转 (互不影响), Set 记录当前翻开的维度
  // 切换小区时收起展开的分类与翻开的评分卡: 由父组件以 community_id 作为 key 重挂载本组件实现
  const [flippedScores, setFlippedScores] = useState<Set<ScoreCardKey>>(new Set());

  const toggleScoreCard = useCallback((key: ScoreCardKey) => {
    setFlippedScores(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  return (
    <div className="community-popup open animate-fade-in">
      <div className="popup-header">
        <div>
          <span className="popup-title">{community.community_name}</span>
          <span className="popup-subdistrict">{community.subdistrict}</span>
        </div>
        <div className="popup-score">
          <span className="score-badge">{community.score.total_score}</span>
          <span className="score-label">综合评分</span>
        </div>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      {/* 房价 4 项: 一行紧凑数字条 */}
      <div className="popup-price-row">
        <div className="stat-cell">
          <div className="stat-label">挂牌均价</div>
          <div className="stat-value">{fmtCompact(community.price.listing_avg_price)}</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">签约均价</div>
          <div className="stat-value">{fmtCompact(community.price.deal_avg_price)}</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">在售套数</div>
          <div className="stat-value">{community.price.listing_count ?? '-'}</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">近月签约</div>
          <div className="stat-value">{community.price.deal_count ?? '-'}</div>
        </div>
      </div>

      {/* 评分维度 2×2 大卡: 可点击翻转看明细, 宽度翻倍解决明细显示不下 */}
      <div className="score-grid">
        <ScoreCard
          label="区位" icon="📍"
          score={community.score.location_score}
          detail={<SubwayDetail subway={community.nearest_subway} />}
          flipped={flippedScores.has('location')}
          onFlip={() => toggleScoreCard('location')}
        />
        <ScoreCard
          label="配套" icon="🛒"
          score={community.score.amenity_score}
          detail={<AmenityDetail pois={poiSorted} />}
          flipped={flippedScores.has('amenity')}
          onFlip={() => toggleScoreCard('amenity')}
        />
        <ScoreCard
          label="产品" icon="🏢"
          score={community.score.product_score}
          detail={<ProductDetail c={community} />}
          flipped={flippedScores.has('product')}
          onFlip={() => toggleScoreCard('product')}
        />
        <ScoreCard
          label="市场" icon="💹"
          score={community.score.market_score}
          detail={<MarketDetail c={community} />}
          flipped={flippedScores.has('market')}
          onFlip={() => toggleScoreCard('market')}
        />
      </div>

      <div className="panel-title">周边配套（1500m内）</div>
      {community.pois.length > 0 ? (
        <>
          <div className="poi-tiles">
            {POI_TILE_TYPES.map(type => {
              const pois = poiSorted[type] || [];
              const config = POI_CONFIG[type as POIType];
              const empty = pois.length === 0;
              const active = expandedPOI === type;
              return (
                <button
                  key={type}
                  className={`poi-tile${active ? ' active' : ''}${empty ? ' empty' : ''}`}
                  style={{ '--tile-color': config.color } as CSSProperties}
                  onClick={() => !empty && setExpandedPOI(active ? null : type)}
                  disabled={empty}
                >
                  <span className="poi-tile-icon">{config.icon}</span>
                  <span className="poi-tile-count">{pois.length}</span>
                  <span className="poi-tile-near">{empty ? '—' : `近${pois[0].distance}m`}</span>
                </button>
              );
            })}
          </div>
          {expandedPOI && (poiSorted[expandedPOI] || []).length > 0 && (
            <div className="poi-tile-list">
              {(poiSorted[expandedPOI] || []).map((poi, idx) => (
                <div key={`${expandedPOI}-${idx}`} className="poi-item">
                  <div className="poi-icon" style={{ backgroundColor: `${POI_CONFIG[expandedPOI as POIType].color}20` }}>
                    {POI_CONFIG[expandedPOI as POIType].icon}
                  </div>
                  <div className="poi-info">
                    <div className="poi-name">{poi.name}</div>
                    <div className="poi-meta">{POI_CONFIG[expandedPOI as POIType].label}</div>
                  </div>
                  <div className="poi-distance">{poi.distance}m</div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div style={{ color: 'var(--text-muted)', fontSize: '13px', padding: '12px 0' }}>
          暂无周边设施数据
        </div>
      )}
    </div>
  );
}

// 主页面组件
export default function BinjiangMapPage() {
  const [activeTab, setActiveTab] = useState<'map' | 'dashboard' | 'market'>('map');
  const [selectedCommunity, setSelectedCommunity] = useState<Community | null>(null);
  // 数据看板"查看"触发的地图定位信号 (key 用时间戳, 同一小区重复点击也能再次触发)
  const [mapFocus, setMapFocus] = useState<{ lng: number; lat: number; key: number } | null>(null);
  const [visiblePOITypes, setVisiblePOITypes] = useState<Set<POIType>>(
    new Set(['subway', 'school', 'mall'] as POIType[])
  );
  const [schoolLevels, setSchoolLevels] = useState<Set<SchoolLevel>>(
    new Set(['primary', 'middle'] as SchoolLevel[])   // 默认只开小学+中学(学区房主场景)
  );
  const [searchQuery, setSearchQuery] = useState('');
  // 默认仅住宅类（与旧后端白名单口径一致，默认视野不变）；商办类需手动勾选类型或"全部"
  const [propertyTypes, setPropertyTypes] = useState<Set<string>>(
    new Set(['住宅', '别墅', '排屋'])
  );
  const [priceMode, setPriceMode] = useState<'all' | 'deal' | 'listing'>('all');
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [communities, setCommunities] = useState<Community[]>([]);
  const [loading, setLoading] = useState(true);
  const [marketReference, setMarketReference] = useState<MarketReference | null>(null);
  const [marketSubdistrict, setMarketSubdistrict] = useState<string | null>(null);

  // 数据看板的筛选/分页/排序状态: 提到主组件, 切到地图不卸载看板组件时仍能保留
  const [dashPage, setDashPage] = useState(1);
  const [dashSubdistrict, setDashSubdistrict] = useState('');
  const [dashPrice, setDashPrice] = useState('');
  const [dashScore, setDashScore] = useState('');
  const [dashSortKey, setDashSortKey] = useState<DashSortKey>('total_score');
  const [dashSortOrder, setDashSortOrder] = useState<'asc' | 'desc'>('desc');
  // 标记"刚从看板点过查看", 地图页显示返回按钮; 点击返回后清除
  const [cameFromDashboard, setCameFromDashboard] = useState(false);

  // 加载小区数据
  useEffect(() => {
    fetchCommunities().then(data => {
      setCommunities(data);
      setLoading(false);
    });
  }, []);

  // 市场行情快照独立加载，失败不会影响地图和看板。
  useEffect(() => {
    fetchMarketReference().then(setMarketReference);
  }, []);

  // 加载地铁路线 + 地铁站 (OSM 数据, 一次即可, 不随筛选变化)
  const [transit, setTransit] = useState<{ routes: import('@/components/map/BinjiangMap').TransitRoute[]; stops: import('@/components/map/BinjiangMap').TransitStop[] } | null>(null);
  useEffect(() => {
    fetch('/api/map/transit').then(r => r.json()).then(d => {
      if (d.success) setTransit(d.data);
    }).catch(() => {});
  }, []);

  // 数据最新快照日期 (取所有价格快照的最大日期, 避免硬编码过期文案)
  const latestSnapshot = useMemo(
    () => communities.reduce((m, c) => (c.price.snapshot_date > m ? c.price.snapshot_date : m), ''),
    [communities]
  );

  const togglePOIType = useCallback((type: POIType) => {
    setVisiblePOITypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const toggleSchoolLevel = useCallback((level: SchoolLevel) => {
    setSchoolLevels(prev => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  }, []);

  const togglePropertyType = useCallback((type: string) => {
    setPropertyTypes(prev => {
      const next = new Set(prev);
      if (type === '全部') {
        // "全部"与其他类型互斥: 点击即重置为全部
        return new Set(['全部']);
      }
      next.delete('全部');
      if (next.has(type)) next.delete(type);
      else next.add(type);
      // 具体类型全部取消时回到"全部"
      if (next.size === 0) next.add('全部');
      return next;
    });
  }, []);

  // —— 价格数据刷新: 触发后台采集 -> 轮询进度 -> 完成后重拉数据 ——
  const [refreshState, setRefreshState] = useState<{
    running: boolean; phase: string; processed: number; total: number; error: string | null;
  } | null>(null);

  const startRefresh = useCallback(async () => {
    try {
      const res = await fetch('/api/map/refresh', { method: 'POST' });
      const d = await res.json();
      if (!d.success) {
        setRefreshState({ running: false, phase: 'error', processed: 0, total: 0, error: d.error });
        return;
      }
      setRefreshState({ running: true, phase: 'fetching', processed: 0, total: d.data.total, error: null });
    } catch {
      setRefreshState({ running: false, phase: 'error', processed: 0, total: 0, error: '触发刷新失败' });
    }
  }, []);

  const stopRefresh = useCallback(async () => {
    try { await fetch('/api/map/refresh', { method: 'DELETE' }); } catch { /* 轮询会拿到终态 */ }
  }, []);

  // —— 小区轮廓重建: 只按当前 OSM 数据重新匹配，不触发房价采集 ——
  const [boundaryState, setBoundaryState] = useState<{
    running: boolean; phase: string; error: string | null;
  } | null>(null);

  const startBoundaryRebuild = useCallback(async () => {
    try {
      const res = await fetch('/api/map/boundaries/rebuild', { method: 'POST' });
      const d = await res.json();
      if (!d.success) {
        setBoundaryState({ running: false, phase: 'error', error: d.error });
        return;
      }
      setBoundaryState({ running: true, phase: 'rebuilding', error: null });
    } catch {
      setBoundaryState({ running: false, phase: 'error', error: '触发轮廓重建失败' });
    }
  }, []);

  useEffect(() => {
    if (!refreshState?.running) return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch('/api/map/refresh');
        const d = await res.json();
        const j = d.data;
        setRefreshState({
          running: j.running, phase: j.phase, processed: j.processed, total: j.total, error: j.error,
        });
        if (j.phase === 'done') {
          const data = await fetchCommunities();
          setCommunities(data);
          setLoading(false);
        }
      } catch { /* 网络抖动, 下个周期重试 */ }
    }, 3000);
    return () => clearInterval(timer);
  }, [refreshState?.running]);

  useEffect(() => {
    if (!boundaryState?.running) return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch('/api/map/boundaries/rebuild');
        const d = await res.json();
        const j = d.data;
        setBoundaryState({ running: j.running, phase: j.phase, error: j.error });
        if (j.phase === 'done') {
          const data = await fetchCommunities();
          setCommunities(data);
          setLoading(false);
        }
      } catch { /* 网络抖动, 下个周期重试 */ }
    }, 1000);
    return () => clearInterval(timer);
  }, [boundaryState?.running]);

  const filteredCommunities = communities.filter(c =>
    c.community_name.toLowerCase().includes(searchQuery.toLowerCase()) &&
    (propertyTypes.has('全部') || propertyTypes.has(c.property_type ?? ''))
  );
  const mapCommunities = marketSubdistrict
    ? filteredCommunities.filter(c => c.subdistrict === marketSubdistrict)
    : filteredCommunities;

  // 跨小区去重后的可见 POI（同一地铁站/学校会出现在多个小区的周边列表里）
  // 地图绘制以滨江区行政边界多边形为地理围栏(矩形 bbox 会误伤钱塘江北岸设施);
  // 弹窗周边配套不受此限, 保留滨江周边宽框数据
  const visiblePOIs = useMemo<MapPOI[]>(() => {
    const seen = new Map<string, MapPOI>();
    for (const c of communities) {
      for (const poi of c.pois) {
        const type = poi.type as MapPOI['type'];
        if (!poi.latitude || !poi.longitude) continue;
        if (!isInBinjiang(poi.longitude, poi.latitude)) continue;

        if (type === 'school') {
          // 学段多选: 培训机构类噪音(null)不绘制
          const level = getSchoolLevel(poi.name);
          if (!level || !schoolLevels.has(level)) continue;
          const key = `${type}|${poi.name}`;
          if (!seen.has(key)) {
            seen.set(key, { name: poi.name, type, latitude: poi.latitude, longitude: poi.longitude, level });
          }
        } else {
          if (!visiblePOITypes.has(type)) continue;
          const key = `${type}|${poi.name}`;
          if (!seen.has(key)) {
            seen.set(key, { name: poi.name, type, latitude: poi.latitude, longitude: poi.longitude });
          }
        }
      }
    }
    return Array.from(seen.values());
  }, [communities, visiblePOITypes, schoolLevels]);

  const handleCommunityClick = useCallback((community: Community) => {
    setSelectedCommunity(community);
  }, []);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <AppHeader
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        latestSnapshot={latestSnapshot}
        refreshState={refreshState}
        onRefresh={startRefresh}
        onStopRefresh={stopRefresh}
        boundaryState={boundaryState}
        onBoundaryRebuild={startBoundaryRebuild}
      />

      {/* Tab 导航 */}
      <div style={{ background: 'var(--bg-surface)', padding: '12px 20px', borderBottom: '1px solid var(--border)' }}>
        <div className="tab-nav">
          <button className={`tab-btn ${activeTab === 'map' ? 'active' : ''}`} onClick={() => setActiveTab('map')}>
            地图查看
          </button>
          <button className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
            数据看板
          </button>
          <button className={`tab-btn ${activeTab === 'market' ? 'active' : ''}`} onClick={() => setActiveTab('market')}>
            市场行情
          </button>
        </div>
      </div>

      <div style={{ flex: 1, position: 'relative', display: 'flex' }}>
        {activeTab === 'market' ? (
          <MarketOverviewPage
            marketReference={marketReference}
            onViewSubdistrict={(subdistrict) => {
              setSelectedCommunity(null);
              setCameFromDashboard(false);
              setMarketSubdistrict(subdistrict);
              setActiveTab('map');
            }}
          />
        ) : activeTab === 'dashboard' ? (
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <DashboardPage
              communities={filteredCommunities}
              searchQuery={searchQuery}
              page={dashPage} setPage={setDashPage}
              subdistrictFilter={dashSubdistrict} setSubdistrictFilter={setDashSubdistrict}
              priceFilter={dashPrice} setPriceFilter={setDashPrice}
              scoreFilter={dashScore} setScoreFilter={setDashScore}
              sortKey={dashSortKey} setSortKey={setDashSortKey}
              sortOrder={dashSortOrder} setSortOrder={setDashSortOrder}
              onView={(c) => {
                setSelectedCommunity(c);
                setCameFromDashboard(true);
                setActiveTab('map');
                if (c.latitude && c.longitude) {
                  setMapFocus({ lng: c.longitude, lat: c.latitude, key: Date.now() });
                }
              }}
            />
          </div>
        ) : (
          <>
            {/* 从看板"查看"过来后, 地图 tab 显示返回按钮 */}
            {cameFromDashboard && (
              <button
                style={{
                  position: 'absolute', top: '16px', left: '50%', transform: 'translateX(-50%)',
                  zIndex: 200,
                  padding: '8px 16px', borderRadius: '999px',
                  background: 'var(--bg-surface)', border: '1px solid var(--accent-warm)',
                  boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
                  fontSize: '13px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: '6px',
                  color: 'var(--accent-warm)',
                }}
                onClick={() => {
                  setSelectedCommunity(null);
                  setCameFromDashboard(false);
                  setActiveTab('dashboard');
                }}
              >
                ← 返回数据看板 (筛选保留)
              </button>
            )}
            {marketSubdistrict && (
              <div className="market-map-filter" role="status">
                <span>正在查看：{marketSubdistrict}</span>
                <button onClick={() => setMarketSubdistrict(null)} aria-label="清除市场行情地图筛选">清除</button>
              </div>
            )}
            {loading ? (
              <div style={{
                position: 'absolute', inset: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--text-muted)', fontSize: '14px',
              }}>
                加载地图数据中...
              </div>
            ) : (
              <BinjiangMap
                communities={mapCommunities}
                pois={visiblePOIs}
                transit={transit ?? undefined}
                onCommunityClick={handleCommunityClick}
                selectedCommunity={selectedCommunity}
                focus={mapFocus}
                priceMode={priceMode}
              />
            )}

            {/* 控制栏收起把手 */}
            <button
              className={`panel-toggle ${panelCollapsed ? 'collapsed' : ''}`}
              onClick={() => setPanelCollapsed(v => !v)}
              title={panelCollapsed ? '展开控制栏' : '收起控制栏'}
            >
              {panelCollapsed ? '‹' : '›'}
            </button>

            {/* 右侧控制面板 */}
            <div className={`control-panel ${panelCollapsed ? 'collapsed' : ''}`}>
              <div className="panel-section">
                <div className="panel-title">POI 图层</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {(Object.entries(POI_CONFIG) as [POIType, typeof POI_CONFIG[POIType]][])
                    .filter(([type]) => type !== 'bus' && type !== 'school')
                    .map(([type, config]) => (
                    <button
                      key={type}
                      className={`poi-toggle ${visiblePOITypes.has(type) ? 'active' : ''}`}
                      onClick={() => togglePOIType(type)}
                    >
                      <span className="dot" style={{ backgroundColor: config.color }} />
                      <span>{config.icon} {config.label}</span>
                    </button>
                  ))}

                  <div style={{ marginTop: '4px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '4px 0' }}>🏫 学校（按学段）</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {(Object.entries(SCHOOL_LEVEL_LABELS) as [SchoolLevel, string][]).map(([level, label]) => (
                        <button
                          key={level}
                          className={`poi-toggle ${schoolLevels.has(level) ? 'active' : ''}`}
                          style={{ padding: '4px 10px', fontSize: '12px' }}
                          onClick={() => toggleSchoolLevel(level)}
                        >
                          <span className="dot" style={{ backgroundColor: SCHOOL_LEVEL_COLORS[level] }} />
                          <span>{label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="panel-section">
                <div className="panel-title">价格口径</div>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '4px' }}>
                  {([['all', '全部'], ['deal', '仅签约价'], ['listing', '仅挂牌价']] as const).map(([mode, label]) => (
                    <button
                      key={mode}
                      className={`poi-toggle ${priceMode === mode ? 'active' : ''}`}
                      style={{ padding: '4px 10px', fontSize: '12px' }}
                      onClick={() => setPriceMode(mode)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  {priceMode === 'all' && '签=成交价, 挂=要价, 成交价通常低于要价 10-20%; 混合显示时跨小区比色注意口径'}
                  {priceMode === 'deal' && '仅显示有签约价的小区(真实成交口径), 其余灰色'}
                  {priceMode === 'listing' && '仅显示有挂牌价的小区(房东要价口径), 其余灰色'}
                </div>
              </div>

              <div className="panel-section">
                <div className="panel-title">物业类型</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
                  {['全部', '住宅', '别墅', '排屋', '写字楼', '公寓', '商贸', '其他'].map(type => (
                    <button
                      key={type}
                      className={`poi-toggle ${propertyTypes.has(type) ? 'active' : ''}`}
                      style={{ padding: '4px 10px', fontSize: '12px' }}
                      onClick={() => togglePropertyType(type)}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* 图例 */}
            <div style={{
              position: 'absolute', bottom: '16px', left: '16px',
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              borderRadius: '8px', padding: '12px',
            }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                价格区间
                <span style={{ marginLeft: '6px' }}>
                  (签 {mapCommunities.filter(c => c.price.deal_avg_price != null).length} / 挂 {mapCommunities.filter(c => c.price.listing_avg_price != null).length})
                </span>
              </div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#3D9147' }} />
                  <span style={{ fontSize: '11px' }}>&lt;2万</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#A8C03C' }} />
                  <span style={{ fontSize: '11px' }}>&lt;3万5</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#E5B32C' }} />
                  <span style={{ fontSize: '11px' }}>3.5-5万</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#E2711D' }} />
                  <span style={{ fontSize: '11px' }}>5-7万</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#D64545' }} />
                  <span style={{ fontSize: '11px' }}>&gt;7万</span>
                </div>
              </div>
            </div>

            {selectedCommunity && (
              <CommunityPopup
                key={selectedCommunity.community_id}
                community={selectedCommunity}
                onClose={() => setSelectedCommunity(null)}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function formatMarketChange(value: number): { text: string; tone: 'up' | 'down' | 'flat' } {
  if (value > 0) return { text: `↑ ${value.toFixed(2)}%`, tone: 'up' };
  if (value < 0) return { text: `↓ ${Math.abs(value).toFixed(2)}%`, tone: 'down' };
  return { text: '— 持平', tone: 'flat' };
}

function MarketOverviewPage({
  marketReference,
  onViewSubdistrict,
}: {
  marketReference: MarketReference | null;
  onViewSubdistrict: (subdistrict: string) => void;
}) {
  if (!marketReference) {
    return <div className="market-overview market-empty">正在加载市场参考数据…</div>;
  }

  if (!marketReference.available) {
    return (
      <div className="market-overview market-empty">
        <div className="market-kicker">MARKET REFERENCE</div>
        <h1>暂无市场参考数据</h1>
        <p>地图与数据看板仍可正常使用；待维护者补充并校验最新挂牌参考快照。</p>
      </div>
    );
  }

  const mom = formatMarketChange(marketReference.overall.mom_percent);
  const yoy = formatMarketChange(marketReference.overall.yoy_percent);
  return (
    <main className="market-overview">
      <section className="market-hero">
        <div>
          <div className="market-kicker">MARKET REFERENCE · {marketReference.scope}</div>
          <h1>滨江市场行情 <span>挂牌参考</span></h1>
          <p className="market-source">
            数据来源：<a href={marketReference.source.url} target="_blank" rel="noreferrer">{marketReference.source.name}</a>
            <span>快照日期：{marketReference.source.captured_at}</span>
          </p>
        </div>
        <p className="market-disclaimer">挂牌参考价反映当前卖方报价，不是网签成交价。</p>
      </section>

      <section className="market-summary" aria-label="滨江挂牌参考概览">
        <article className="market-card market-price-card">
          <div className="market-card-label">滨江挂牌参考均价</div>
          <strong>{marketReference.overall.avg_price.toLocaleString()}</strong>
          <span>元 / ㎡</span>
        </article>
        <article className="market-card">
          <div className="market-card-label">环比</div>
          <strong className={`market-change ${mom.tone}`}>{mom.text}</strong>
          <span>相较上月</span>
        </article>
        <article className="market-card">
          <div className="market-card-label">同比</div>
          <strong className={`market-change ${yoy.tone}`}>{yoy.text}</strong>
          <span>相较去年同期</span>
        </article>
      </section>

      <section className="market-table-panel">
        <div className="market-section-head">
          <div>
            <div className="market-kicker">SOURCE LABELS</div>
            <h2>热门商圈挂牌参考</h2>
          </div>
          <p>商圈为来源页面标签；地图按街道近似查看。</p>
        </div>
        <div className="market-table-wrap">
          <table className="market-table">
            <thead>
              <tr><th>来源商圈</th><th>挂牌参考均价</th><th>环比</th><th>地图查看</th></tr>
            </thead>
            <tbody>
              {marketReference.subdistricts.map((row) => {
                const change = formatMarketChange(row.mom_percent);
                return (
                  <tr key={row.name}>
                    <td><strong>{row.name}</strong><small>{row.map_scope_note}</small></td>
                    <td className="market-price-cell">{row.avg_price.toLocaleString()} <span>元 / ㎡</span></td>
                    <td><span className={`market-change ${change.tone}`}>{change.text}</span></td>
                    <td><button className="market-view-btn" onClick={() => onViewSubdistrict(row.map_subdistrict)}>查看 {row.map_subdistrict}</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <p className="market-footnote">口径说明：挂牌均价适合观察区域卖方报价变化，可能与透明售房网的小区网签/成交数据不同。</p>
    </main>
  );
}

// 数据看板页面
type DashSortKey = 'total_score' | 'price' | 'name' | 'build_year' | 'property_fee' | 'parking_ratio' | 'subway';

// ———————————————————————————————————————————————————————————
// 弹窗内的可翻转评分卡片: 正面只显示分数, 翻到背面看具体指标明细
// ———————————————————————————————————————————————————————————
type ScoreCardKey = 'location' | 'amenity' | 'product' | 'market';

// 区位详情 (背面)
function SubwayDetail({ subway }: { subway: Community['nearest_subway'] }) {
  if (!subway) return <div className="score-detail-empty">无地铁站数据, 区位分无法计算</div>;
  const tier = subway.distance <= 400 ? '步行直达 (400m 内)'
    : subway.distance <= 800 ? '近距离 (800m 内)'
    : subway.distance <= 1500 ? '可达 (1.5km 内)'
    : '偏远 (>1.5km)';
  return (
    <div className="score-detail">
      <div className="score-detail-row">
        <span className="score-detail-label">最近地铁</span>
        <span className="score-detail-val">{subway.name}</span>
      </div>
      <div className="score-detail-row">
        <span className="score-detail-label">距离</span>
        <span className="score-detail-val">{subway.distance} m</span>
      </div>
      <div className="score-detail-row">
        <span className="score-detail-label">档位</span>
        <span className="score-detail-val">{tier}</span>
      </div>
    </div>
  );
}

// 配套详情 (背面): 5 类 POI 的数量 + 最近距离
const POI_LABELS_BACK: Record<POIType, string> = {
  subway: '地铁', school: '学校', hospital: '医院', mall: '商场', park: '公园', bus: '公交',
};
function AmenityDetail({ pois }: { pois: Partial<Record<POIType, Community['pois']>> }) {
  const types: POIType[] = ['subway', 'school', 'hospital', 'mall', 'park'];
  const rows = types.map(t => {
    const list = pois[t] || [];
    const nearest = list.length ? `近 ${list[0].distance} m` : '无';
    return { t, count: list.length, nearest };
  });
  const total = (Object.values(pois) as Community['pois'][]).reduce((s, l) => s + (l?.length || 0), 0);
  // 两列网格: 每格标签在上、数值在下, 6 项只占 3 行, 宽卡下无需滚动
  return (
    <div className="score-detail score-detail-grid2">
      {rows.map(r => (
        <div key={r.t} className="score-detail-cell">
          <span className="score-detail-label">{POI_LABELS_BACK[r.t]}</span>
          <span className="score-detail-val">{r.count} 所 · {r.nearest}</span>
        </div>
      ))}
      <div className="score-detail-cell score-detail-full">
        <span className="score-detail-label">合计</span>
        <span className="score-detail-val">{total} 个</span>
      </div>
    </div>
  );
}

// 产品详情 (背面): 楼龄/容积率/车位比/物业费/绿化率, 缺则不显示
function ProductDetail({ c }: { c: Community }) {
  const age = c.build_year ? new Date().getFullYear() - c.build_year : null;
  const rows: Array<{ k: string; v: string }> = [];
  if (age != null) rows.push({ k: '楼龄', v: `${age} 年 (${c.build_year} 建)` });
  if (c.parking_ratio != null) rows.push({ k: '车位比', v: `${c.parking_ratio} (车户比)` });
  if (c.property_fee != null) rows.push({ k: '物业费', v: `${c.property_fee} 元/㎡/月` });
  if (c.far_ratio != null) rows.push({ k: '容积率', v: `${c.far_ratio}` });
  if (c.greening_rate != null) rows.push({ k: '绿化率', v: `${c.greening_rate}%` });
  if (rows.length === 0) return <div className="score-detail-empty">产品数据缺失, 评分无法计算</div>;
  // 两列网格: 5 项占 3 行, 与配套卡同样的紧凑排布
  return (
    <div className="score-detail score-detail-grid2">
      {rows.map(r => (
        <div key={r.k} className="score-detail-cell">
          <span className="score-detail-label">{r.k}</span>
          <span className="score-detail-val">{r.v}</span>
        </div>
      ))}
    </div>
  );
}

// 市场详情 (背面): 签约套数 + 在售 + 价格 + 签/挂标记
function MarketDetail({ c }: { c: Community }) {
  const deal = c.price.deal_count ?? null;
  const list = c.price.listing_count ?? null;
  const isDealPrice = c.price.deal_avg_price != null;
  const price = c.price.deal_avg_price ?? c.price.listing_avg_price;
  return (
    <div className="score-detail">
      <div className="score-detail-row">
        <span className="score-detail-label">近30日签约</span>
        <span className="score-detail-val">{deal != null ? `${deal} 套` : '-'}</span>
      </div>
      <div className="score-detail-row">
        <span className="score-detail-label">在售套数</span>
        <span className="score-detail-val">{list != null ? `${list} 套` : '-'}</span>
      </div>
      <div className="score-detail-row">
        <span className="score-detail-label">价格口径</span>
        <span className="score-detail-val">{price != null ? `${price.toLocaleString()} 元/㎡ ${isDealPrice ? '签约' : '挂牌'}` : '无'}</span>
      </div>
    </div>
  );
}

// 翻转卡片组件: 正面只有分数, 背面是具体指标明细
// transition 期间 (0.6s) 锁定点击, 防止快速重复点击导致状态错位
function ScoreCard({
  label, icon, score, detail, flipped, onFlip,
}: {
  label: string; icon: string;
  score: number | null | undefined;
  detail: ReactNode;
  flipped: boolean;
  onFlip: () => void;
}) {
  const lockRef = useRef(false);
  const handleFlip = () => {
    if (lockRef.current) return;
    lockRef.current = true;
    onFlip();
    setTimeout(() => { lockRef.current = false; }, 650);
  };
  // 容器复用 .stat-cell 的视觉 (背景/边框/圆角), 在 2×2 score-grid 中占半宽
  // 内层 .score-card-face 绝对定位铺满, 翻转时保持视觉一致
  const barPct = Math.max(0, Math.min(100, score ?? 0));
  return (
    <div className={`stat-cell score-card ${flipped ? 'flipped' : ''}`} onClick={handleFlip} title={flipped ? '点击翻回正面' : '点击查看明细'}>
      <div className="score-card-face score-card-front">
        <div className="score-card-head">
          <span className="score-card-icon">{icon}</span>
          <span className="score-card-label">{label}</span>
          <span className="score-card-score">{score ?? '—'}</span>
        </div>
        <div className="score-card-bar" aria-hidden="true">
          <div className="score-card-bar-fill" style={{ width: `${barPct}%` }} />
        </div>
        <div className="score-card-hint">{flipped ? '点击翻回正面' : '点击看明细'}</div>
      </div>
      <div className="score-card-face score-card-back">
        <div className="score-card-back-label">{label} · 明细</div>
        {detail}
      </div>
    </div>
  );
}

// 顶部 header (Logo/搜索/价格数据/刷新), 地图页与看板共用同一份, 切 tab 时不重挂载
function AppHeader({
  searchQuery,
  onSearchChange,
  latestSnapshot,
  refreshState,
  onRefresh,
  onStopRefresh,
  boundaryState,
  onBoundaryRebuild,
}: {
  searchQuery: string;
  onSearchChange: (v: string) => void;
  latestSnapshot: string;
  refreshState: { running: boolean; phase: string; processed: number; total: number; error: string | null } | null;
  onRefresh: () => void;
  onStopRefresh: () => void;
  boundaryState: { running: boolean; phase: string; error: string | null } | null;
  onBoundaryRebuild: () => void;
}) {
  return (
    <header style={{
      height: '64px',
      background: 'var(--bg-surface)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 20px',
      gap: '24px',
    }}>
      {/* 站点首页在 basePath 之外，Next Link 会将 / 拼成 /map。 */}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <a href="/" className="back-home">← 返回首页</a>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{
          width: '32px', height: '32px',
          background: 'linear-gradient(135deg, var(--accent-warm), var(--accent-gold))',
          borderRadius: '8px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '18px',
        }}>🏠</div>
        <span style={{ fontSize: '18px', fontWeight: '700', fontFamily: 'var(--font-display)' }}>
          滨房地图
        </span>
      </div>

      <input
        type="text"
        className="search-input"
        placeholder="搜索小区名称..."
        value={searchQuery}
        onChange={e => onSearchChange(e.target.value)}
      />

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '16px' }}>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          价格数据: {latestSnapshot || '—'}
          {refreshState?.running && (
            <span style={{ marginLeft: '8px', color: 'var(--accent-warm)' }}>
              刷新中 {refreshState.processed}/{refreshState.total}…
            </span>
          )}
          {refreshState && !refreshState.running && refreshState.phase === 'done' && (
            <span style={{ marginLeft: '8px', color: 'var(--price-down)' }}>已更新</span>
          )}
          {refreshState && !refreshState.running && refreshState.phase === 'cancelled' && (
            <span style={{ marginLeft: '8px' }}>已停止(数据未改动)</span>
          )}
          {refreshState && !refreshState.running && refreshState.phase === 'error' && (
            <span style={{ marginLeft: '8px', color: 'var(--price-up)' }} title={refreshState.error ?? ''}>
              刷新失败
            </span>
          )}
          {boundaryState?.running && (
            <span style={{ marginLeft: '8px', color: 'var(--accent-warm)' }}>轮廓重建中…</span>
          )}
          {boundaryState && !boundaryState.running && boundaryState.phase === 'done' && (
            <span style={{ marginLeft: '8px', color: 'var(--price-down)' }}>轮廓已更新</span>
          )}
          {boundaryState && !boundaryState.running && boundaryState.phase === 'error' && (
            <span style={{ marginLeft: '8px', color: 'var(--price-up)' }} title={boundaryState.error ?? ''}>
              轮廓重建失败
            </span>
          )}
        </span>
        {refreshState?.running ? (
          <button className="btn btn-secondary" onClick={onStopRefresh}>
            <span>⏹</span> 停止
          </button>
        ) : (
          <button className="btn btn-secondary" onClick={onRefresh}>
            <span>🔄</span> 刷新
          </button>
        )}
        <button
          className="btn btn-secondary"
          onClick={onBoundaryRebuild}
          disabled={boundaryState?.running}
          title="按当前 OSM 数据重新匹配小区轮廓，不更新房价"
        >
          <span>🗺️</span> {boundaryState?.running ? '重建中' : '重建轮廓'}
        </button>
      </div>
    </header>
  );
}

// 表头单元格: 带点击排序 + 方向箭头 (模块顶层组件, 排序态经 props 传入, 避免渲染期重建)
function Th({
  label, k, align, sortKey, sortOrder, onToggle,
}: {
  label: string;
  k?: DashSortKey;
  align?: 'right';
  sortKey: DashSortKey;
  sortOrder: 'asc' | 'desc';
  onToggle: (key: DashSortKey) => void;
}) {
  return (
    <th
      style={{ cursor: k ? 'pointer' : 'default', textAlign: align, userSelect: 'none' }}
      onClick={k ? () => onToggle(k) : undefined}
      title={k ? '点击排序' : undefined}
    >
      {label}
      {k && sortKey === k && <span style={{ marginLeft: '2px' }}>{sortOrder === 'desc' ? '↓' : '↑'}</span>}
    </th>
  );
}

function DashboardPage({
  communities,
  onView,
  header,
  searchQuery,
  page, setPage,
  subdistrictFilter, setSubdistrictFilter,
  priceFilter, setPriceFilter,
  scoreFilter, setScoreFilter,
  sortKey, setSortKey,
  sortOrder, setSortOrder,
}: {
  communities: Community[];
  onView: (c: Community) => void;
  header?: ReactNode;
  searchQuery: string;
  page: number; setPage: (v: number | ((p: number) => number)) => void;
  subdistrictFilter: string; setSubdistrictFilter: (v: string) => void;
  priceFilter: string; setPriceFilter: (v: string) => void;
  scoreFilter: string; setScoreFilter: (v: string) => void;
  sortKey: DashSortKey; setSortKey: (v: DashSortKey | ((k: DashSortKey) => DashSortKey)) => void;
  sortOrder: 'asc' | 'desc'; setSortOrder: (v: 'asc' | 'desc' | ((o: 'asc' | 'desc') => 'asc' | 'desc')) => void;
}) {

  const pageSize = 50;

  const toggleSort = (key: DashSortKey) => {
    if (sortKey === key) {
      setSortOrder(o => (o === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortKey(key);
      setSortOrder(key === 'name' ? 'asc' : 'desc');
    }
    setPage(1);
  };

  // 排序取值: null(无数据)参与比较时永远沉底
  const sortValOf = (c: Community, key: DashSortKey): string | number | null => {
    switch (key) {
      case 'total_score': return c.score?.total_score ?? null;
      case 'price': return getDisplayPrice(c.price);
      case 'name': return c.community_name;
      case 'build_year': return c.build_year ?? null;
      case 'property_fee': return c.property_fee ?? null;
      case 'parking_ratio': return c.parking_ratio ?? null;
      case 'subway': return c.nearest_subway?.distance ?? null;
    }
  };

  // 应用筛选
  const filtered = communities.filter(c => {
    if (subdistrictFilter && c.subdistrict !== subdistrictFilter) return false;
    if (priceFilter) {
      const price = getDisplayPrice(c.price) || 0;
      if (priceFilter === '0-20000' && (price < 20000 || price === 0)) return false;
      if (priceFilter === '20000-35000' && (price < 20000 || price >= 35000)) return false;
      if (priceFilter === '35000-50000' && (price < 35000 || price >= 50000)) return false;
      if (priceFilter === '50000-999999' && price < 50000) return false;
    }
    if (scoreFilter) {
      const score = c.score?.total_score || 0;
      if (scoreFilter === '80-100' && score < 80) return false;
      if (scoreFilter === '60-80' && (score < 60 || score >= 80)) return false;
      if (scoreFilter === '0-60' && score >= 60) return false;
    }
    if (searchQuery && !c.community_name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  }).sort((a, b) => {
    const aVal = sortValOf(a, sortKey);
    const bVal = sortValOf(b, sortKey);
    if (typeof aVal === 'string' || typeof bVal === 'string') {
      return sortOrder === 'desc'
        ? String(bVal).localeCompare(String(aVal))
        : String(aVal).localeCompare(String(bVal));
    }
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;
    return sortOrder === 'desc' ? bVal - aVal : aVal - bVal;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);

  const latestSnapshot = communities.reduce((m, c) => (c.price.snapshot_date > m ? c.price.snapshot_date : m), '');

  const priceOf = (c: Community) => getDisplayPrice(c.price) || 0;
  const stats = {
    total: filtered.length,
    avgPrice: filtered.length ? Math.round(filtered.reduce((sum, c) => sum + priceOf(c), 0) / filtered.length) : null,
    dealCount: filtered.reduce((sum, c) => sum + (c.price.deal_count || 0), 0),
    withPrice: filtered.filter(c => getDisplayPrice(c.price) != null).length,
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {header}

      {/* 统计卡片 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '16px',
        padding: '20px',
        background: 'var(--bg-primary)',
      }}>
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">小区总数</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.avgPrice?.toLocaleString() ?? '—'}</div>
          <div className="stat-label">平均价格 (元/㎡)</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.dealCount}</div>
          <div className="stat-label">近30日签约 (套)</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.withPrice}</div>
          <div className="stat-label">有价格数据的小区</div>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="filter-bar">
        <select className="select-input" value={subdistrictFilter} onChange={e => { setSubdistrictFilter(e.target.value); setPage(1); }}>
          <option value="">全部板块</option>
          <option value="浦沿">浦沿</option>
          <option value="长河">长河</option>
          <option value="西兴">西兴</option>
        </select>
        <select className="select-input" value={priceFilter} onChange={e => { setPriceFilter(e.target.value); setPage(1); }}>
          <option value="">价格区间</option>
          <option value="0-20000">2万以下</option>
          <option value="20000-35000">2-3.5万</option>
          <option value="35000-50000">3.5-5万</option>
          <option value="50000-999999">5万以上</option>
        </select>
        <select className="select-input" value={scoreFilter} onChange={e => { setScoreFilter(e.target.value); setPage(1); }}>
          <option value="">评分区间</option>
          <option value="80-100">80分以上</option>
          <option value="60-80">60-80分</option>
          <option value="0-60">60分以下</option>
        </select>
      </div>

      {/* 数据表格 */}
      <div style={{ flex: 1, padding: '0 20px 20px', overflow: 'auto' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', padding: '0 2px 8px', lineHeight: 1.7 }}>
          口径说明：价格数据取自透明售房网（{latestSnapshot} 采集）。<b>挂</b> = 挂牌均价（在售房源标价均值）；
          <b>签</b> = 签约均价（月签约走势的最新一个月均价，即最近一个有成交的月份，可能滞后于当前月份）；
          近30日签约为滚动 30 天口径，0 套代表近 30 天无成交、不代表更早无成交；综合评分的市场面维度即基于该签约套数。
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <Th label="小区名" k="name" sortKey={sortKey} sortOrder={sortOrder} onToggle={toggleSort} />
              <th>板块</th>
              <th>物业类型</th>
              <Th label="均价 (元/㎡)" k="price" sortKey={sortKey} sortOrder={sortOrder} onToggle={toggleSort} />
              <Th label="综合评分" k="total_score" sortKey={sortKey} sortOrder={sortOrder} onToggle={toggleSort} />
              <Th label="最近地铁" k="subway" sortKey={sortKey} sortOrder={sortOrder} onToggle={toggleSort} />
              <Th label="建成年代" k="build_year" sortKey={sortKey} sortOrder={sortOrder} onToggle={toggleSort} />
              <Th label="物业费" k="property_fee" sortKey={sortKey} sortOrder={sortOrder} onToggle={toggleSort} />
              <Th label="车位比" k="parking_ratio" sortKey={sortKey} sortOrder={sortOrder} onToggle={toggleSort} />
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {paginated.map(community => {
              const isDeal = community.price.deal_avg_price != null;
              const score = community.score;
              return (
                <tr key={community.community_id}>
                  <td style={{ fontWeight: '500' }}>{community.community_name}</td>
                  <td>
                    <span className="tag tag-subway">{community.subdistrict}</span>
                  </td>
                  <td>
                    <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: 'var(--bg-primary)', color: 'var(--text-muted)' }}>{community.property_type || '-'}</span>
                  </td>
                  <td style={{ fontWeight: '600', color: getPriceColor(getDisplayPrice(community.price)) }}>
                    {getDisplayPrice(community.price)?.toLocaleString() || '-'}
                    {getDisplayPrice(community.price) != null && (
                      <span style={{
                        marginLeft: '4px', fontSize: '10px', padding: '1px 4px', borderRadius: '3px',
                        background: isDeal ? 'rgba(194, 117, 88, 0.15)' : 'var(--bg-primary)',
                        color: isDeal ? 'var(--accent-warm)' : 'var(--text-muted)',
                      }}>{isDeal ? '签' : '挂'}</span>
                    )}
                  </td>
                  <td>
                    <span style={{ color: 'var(--accent-gold)', fontWeight: '700' }}>{score?.total_score ?? '-'}</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>/100</span>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px', whiteSpace: 'nowrap' }}
                      title="区位/配套/产品力/市场面 分项得分">
                      区{score?.location_score ?? '—'} 配{score?.amenity_score ?? '—'} 产{score?.product_score ?? '—'} 市{score?.market_score ?? '—'}
                    </div>
                  </td>
                  <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                    {community.nearest_subway
                      ? <>{community.nearest_subway.name} <span style={{ fontSize: '11px' }}>{community.nearest_subway.distance}m</span></>
                      : '-'}
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>{community.build_year ?? '-'}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{community.property_fee != null ? `${community.property_fee}元` : '-'}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{community.parking_ratio ?? '-'}</td>
                  <td>
                    <button className="btn btn-secondary" style={{ padding: '4px 12px', fontSize: '12px' }} onClick={() => onView(community)}>
                      查看
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
        <span>第 {page} / {totalPages} 页</span>
        <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
      </div>
    </div>
  );
}
