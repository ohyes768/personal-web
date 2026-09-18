'use client';

import { useEffect, useRef, useState } from 'react';
import type { Community, MapPOI } from '@/lib/types';
import { getDisplayPrice, getPriceColor, SCHOOL_LEVEL_COLORS, SCHOOL_LEVEL_LABELS } from '@/lib/types';

export interface TransitRoute {
  id: string;
  ref: string;        // 如 "1"、"4"、"6"
  name: string;       // 如 "1号线：湘湖 -> 萧山国际机场"
  colour: string;     // OSM 官方颜色, 如 "#df4661"
  path: number[][];   // GCJ-02 坐标
}

export interface TransitStop {
  name: string;
  lng: number;
  lat: number;
}

interface BinjiangMapProps {
  communities: Community[];
  pois?: MapPOI[];
  transit?: { routes: TransitRoute[]; stops: TransitStop[] };
  onCommunityClick: (community: Community) => void;
  selectedCommunity?: Community | null;
  focus?: { lng: number; lat: number; key: number } | null; // 外部触发的飞行定位信号
  priceMode?: 'all' | 'deal' | 'listing'; // 价格口径: 混合 / 仅签约价 / 仅挂牌价(不匹配的小区显示灰色)
}

const GAODE_MAP_KEY = process.env.NEXT_PUBLIC_GAODE_MAP_KEY || '';
const BINJIANG_CENTER: [number, number] = [120.17, 30.18];

// POI 圆点配色，与 page.tsx 的 POI_CONFIG 保持一致 (浅色底图上适当加深保证对比度)
const POI_MARKER_COLORS: Record<string, string> = {
  subway: '#3B76D2',
  school: '#6C5CE7',
  hospital: '#D94F7E',
  mall: '#DE8F0E',
  park: '#2E9E55',
  bus: '#4899BE',
};

// POI 图标 (白色剪影, viewBox 24, 内嵌 12px)
const POI_ICONS: Record<string, string> = {
  // 列车正面
  subway: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M6 3h12a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V5a2 2 0 012-2zm0 3v6h12V6H6zm2.5 9.5a1.25 1.25 0 100 2.5 1.25 1.25 0 000-2.5zm7 0a1.25 1.25 0 100 2.5 1.25 1.25 0 000-2.5z"/></svg>',
  // 学位帽 (学段以底色深浅区分)
  school: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M12 3 1 9l11 6 9-4.91V17h2V9L12 3zm-5 8.6V15c0 1.7 2.2 3 5 3s5-1.3 5-3v-3.4l-5 2.7-5-2.7z"/></svg>',
  // 医疗十字
  hospital: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M9.5 3h5v6.5H21v5h-6.5V21h-5v-6.5H3v-5h6.5V3z"/></svg>',
  // 购物袋
  mall: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M12 2a5 5 0 015 5v1h3l1.5 13H2.5L4 8h3V7a5 5 0 015-5zm0 2a3 3 0 00-3 3v1h6V7a3 3 0 00-3-3z"/></svg>',
  // 树
  park: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M12 2l5.5 8H15l4 6h-5v5h-4v-5H5l4-6H6.5L12 2z"/></svg>',
  bus: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M5 3h14a2 2 0 012 2v11a2 2 0 01-2 2h-1v2h-3v-2H9v2H6v-2H5a2 2 0 01-2-2V5a2 2 0 012-2zm1 3v7h12V6H6zm1.5 9.5a1.25 1.25 0 100 2.5 1.25 1.25 0 000-2.5zm9 0a1.25 1.25 0 100 2.5 1.25 1.25 0 000-2.5z"/></svg>',
};

// POI 标记随缩放切换: 低缩放(全区视野)用小圆点, 高缩放(社区视野)用图标, 避免密集时糊成一片
const POI_ICON_MIN_ZOOM = 14;

function buildPOIDotContent(color: string): string {
  return `<div style="width:8px;height:8px;border-radius:50%;background:${color};border:1px solid rgba(255,255,255,0.8);box-shadow:0 0 3px rgba(0,0,0,0.4)"></div>`;
}

function buildPOIIconContent(color: string, icon: string): string {
  return `<div style="width:20px;height:20px;border-radius:50%;background:${color};border:1.5px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center">${icon}</div>`;
}

// POI 类型中文标签 (信息窗展示用)
const POI_TYPE_LABELS: Record<string, string> = {
  subway: '地铁站',
  school: '学校',
  hospital: '医院',
  mall: '商场',
  park: '公园',
  bus: '公交站',
};

function buildPOIInfoContent(poi: MapPOI, color: string): string {
  const label = poi.type === 'school' && poi.level
    ? `${SCHOOL_LEVEL_LABELS[poi.level]} · 学校`
    : (POI_TYPE_LABELS[poi.type] || poi.type);
  return `<div style="padding:6px 10px;min-width:130px">
    <div style="font-size:14px;font-weight:600;color:#1c2434;line-height:1.4">${poi.name}</div>
    <div style="font-size:12px;color:#5a6478;margin-top:3px;display:flex;align-items:center;gap:6px">
      <span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block;flex:none"></span>${label}
    </div>
  </div>`;
}

declare global {
  interface Window {
    AMap: any;
    _amapSecurityConfig: any;
  }
}

export default function BinjiangMap({ communities, pois, transit, onCommunityClick, selectedCommunity, focus, priceMode = 'all' }: BinjiangMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const polygonsRef = useRef<any[]>([]);
  const polygonByCommIdRef = useRef<Map<string, any>>(new Map());
  const commByCidRef = useRef<Map<string, Community>>(new Map());
  const circleRef = useRef<any>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const selectedIdRef = useRef<string | null>(null);
  const poiMarkersRef = useRef<any[]>([]);
  const poiMarkerStylesRef = useRef<{ marker: any; dot: string; full: string }[]>([]);
  const poiInfoWindowRef = useRef<any>(null);
  const transitLinesRef = useRef<any[]>([]);
  const transitStopsRef = useRef<any[]>([]);
  const [mapLoaded, setMapLoaded] = useState(false);

  // 供轮廓事件回调读取最新选中态, 避免闭包过期
  useEffect(() => {
    selectedIdRef.current = selectedCommunity?.community_id ?? null;
  }, [selectedCommunity]);

  // 轮廓样式: 全部小区统一透明度/描边(视觉深浅差异只由价格档色阶决定); 选中加粗高亮, 悬停轻度提亮
  const styleOptions = (community: Community, selected: boolean, hovered: boolean) => {
    return {
      fillOpacity: selected ? 0.42 : 0.25 + (hovered ? 0.1 : 0),
      strokeWeight: selected ? 3.5 : hovered ? 2.8 : 1.6,
      strokeOpacity: 0.95,
    };
  };

  // 加载高德地图 JS API
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    if (process.env.NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY) {
      window._amapSecurityConfig = {
        securityJsCode: process.env.NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY,
      };
    }

    const script = document.createElement('script');
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${GAODE_MAP_KEY}&plugin=AMap.Scale,AMap.ToolBar`;
    script.async = true;
    script.onload = () => setMapLoaded(true);
    script.onerror = () => console.error('Failed to load Gaode Maps API');
    document.head.appendChild(script);

    return () => {
      mapInstanceRef.current?.destroy();
      mapInstanceRef.current = null;
    };
  }, []);

  // 初始化地图
  useEffect(() => {
    if (!mapLoaded || !mapRef.current || mapInstanceRef.current) return;

    const map = new window.AMap.Map(mapRef.current, {
      zoom: 13,
      center: BINJIANG_CENTER,
      mapStyle: 'amap://styles/whitesmoke',
      viewMode: '2D',
    });

    map.addControl(new window.AMap.Scale());
    map.addControl(new window.AMap.ToolBar({ position: 'LB' }));
    mapInstanceRef.current = map;
    (window as any).__binjiangMap = map;

    // POI 点击信息窗(单例复用); 点地图任意处关闭(小区轮廓 bubble:true 点击也会冒泡触发关闭)
    poiInfoWindowRef.current = new window.AMap.InfoWindow({
      autoMove: true,
      offset: new window.AMap.Pixel(0, -12),
    });
    map.on('click', () => poiInfoWindowRef.current?.close());

    // 缩放结束后按级别切换 POI 标记样式(小圆点 <-> 图标)
    map.on('zoomend', () => {
      const useIcon = map.getZoom() >= POI_ICON_MIN_ZOOM;
      for (const { marker, dot, full } of poiMarkerStylesRef.current) {
        marker.setContent(useIcon ? full : dot);
      }
    });

    return () => {
      mapInstanceRef.current?.destroy();
      mapInstanceRef.current = null;
    };
  }, [mapLoaded]);

  // 添加小区标记点
  useEffect(() => {
    if (!mapInstanceRef.current || !mapLoaded) return;

    markersRef.current.forEach(m => mapInstanceRef.current.remove(m));
    markersRef.current = [];
    polygonsRef.current.forEach(p => mapInstanceRef.current.remove(p));
    polygonsRef.current = [];
    polygonByCommIdRef.current.clear();
    commByCidRef.current.clear();

    // hover 小提示: 跟随鼠标显示小区名 + 价格
    const showTooltip = (community: Community, pixel?: { x: number; y: number }) => {
      const el = tooltipRef.current;
      if (!el) return;
      const price = getDisplayPrice(community.price);
      // 价格口径角标: 数据源里签约/挂牌互斥, 有签约价标"签", 否则标"挂" (签约价系统性低于挂牌价, 提示口径避免跨小区误比)
      const priceTag = community.price.deal_avg_price != null ? '签' : '挂';
      const priceHtml = price
        ? `${price.toLocaleString()} 元/㎡<span class="tt-tag">${priceTag}</span>`
        : '暂无价格';
      el.innerHTML = `<span class="tt-name">${community.community_name}</span><span class="tt-price">${priceHtml}</span>`;
      el.style.display = 'block';
      if (pixel) moveTooltip(pixel);
    };
    const moveTooltip = (pixel: { x: number; y: number }) => {
      const el = tooltipRef.current;
      if (!el) return;
      el.style.left = `${pixel.x + 14}px`;
      el.style.top = `${Math.max(pixel.y - 36, 4)}px`;
    };
    const hideTooltip = () => {
      if (tooltipRef.current) tooltipRef.current.style.display = 'none';
    };
    // 悬停提亮轮廓 + 显示提示; 移出后按选中态还原
    const bindHover = (overlay: any, community: Community) => {
      overlay.on('mouseover', (ev: any) => {
        overlay.setOptions(styleOptions(community, selectedIdRef.current === community.community_id, true));
        showTooltip(community, ev?.pixel);
      });
      overlay.on('mousemove', (ev: any) => moveTooltip(ev?.pixel));
      overlay.on('mouseout', () => {
        overlay.setOptions(styleOptions(community, selectedIdRef.current === community.community_id, false));
        hideTooltip();
      });
    };

    communities.forEach(community => {
      if (!community.latitude || !community.longitude) return;

      // 价格口径: 'deal'/'listing' 模式下只取对应口径的价格, 无该口径价格的小区显示灰色(保证同色阶内同口径可比)
      const modePrice = priceMode === 'deal' ? community.price.deal_avg_price
        : priceMode === 'listing' ? community.price.listing_avg_price
        : getDisplayPrice(community.price);
      const color = getPriceColor(modePrice);
      commByCidRef.current.set(community.community_id, community);

      // 仅展示 OSM 来源轮廓; Shapefile 来源暂不展示（数据管线保留, boundary_source==='shp'）
      const hasVisiblePolygon = !!(community.boundary && community.boundary.length > 0 && community.boundary_source !== 'shp');
      if (hasVisiblePolygon) {
        const isOSM = community.boundary_source === 'osm';
        const polygon = new window.AMap.Polygon({
          path: community.boundary,
          fillColor: color,
          strokeColor: color,
          strokeStyle: isOSM ? 'dashed' : 'solid',
          strokeDasharray: isOSM ? [8, 6] : undefined,
          cursor: 'pointer',
          bubble: true,
          ...styleOptions(community, false, false),
        });
        polygon.on('click', () => onCommunityClick(community));
        bindHover(polygon, community);
        mapInstanceRef.current.add(polygon);
        polygonsRef.current.push(polygon);
        polygonByCommIdRef.current.set(community.community_id, polygon);
      }

      // 无真实轮廓的小区: 以定位点为中心画 100m×100m 虚线方块占位(约1公顷, 老小区典型组团尺度),
      // 填充较明显 + 中心叠"?"徽标(pointer-events:none 穿透) —— 表示"位置示意, 边界待补"
      if (!hasVisiblePolygon) {
        const halfLat = 50 / 111320;
        const halfLng = 50 / (111320 * Math.cos(30.19 * Math.PI / 180));
        const path = [
          [community.longitude - halfLng, community.latitude - halfLat],
          [community.longitude + halfLng, community.latitude - halfLat],
          [community.longitude + halfLng, community.latitude + halfLat],
          [community.longitude - halfLng, community.latitude + halfLat],
        ];
        const placeholder = new window.AMap.Polygon({
          path,
          fillColor: color,
          strokeColor: color,
          strokeStyle: 'dashed',
          strokeDasharray: [4, 4],
          cursor: 'pointer',
          bubble: true,
          ...styleOptions(community, false, false),
        });
        placeholder.on('click', () => onCommunityClick(community));
        bindHover(placeholder, community);
        mapInstanceRef.current.add(placeholder);
        polygonsRef.current.push(placeholder);
        polygonByCommIdRef.current.set(community.community_id, placeholder);

        const questionMark = new window.AMap.Marker({
          position: [community.longitude, community.latitude],
          anchor: 'center',
          content: `<div style="pointer-events:none;width:14px;height:14px;border-radius:50%;background:rgba(10,14,22,0.8);color:#fff;font-size:10px;line-height:14px;text-align:center;font-weight:700;box-shadow:0 0 3px rgba(0,0,0,0.5)">?</div>`,
        });
        mapInstanceRef.current.add(questionMark);
        markersRef.current.push(questionMark);
      }
    });
  }, [communities, mapLoaded, onCommunityClick, priceMode]);

  // 地铁路线 + 地铁站 (在小区轮廓之下)
  useEffect(() => {
    if (!mapInstanceRef.current || !mapLoaded || !transit) return;

    transitLinesRef.current.forEach(l => mapInstanceRef.current.remove(l));
    transitStopsRef.current.forEach(s => mapInstanceRef.current.remove(s));
    transitLinesRef.current = [];
    transitStopsRef.current = [];

    transit.routes.forEach(route => {
      const colour = route.colour || '#3B76D2';
      const line = new window.AMap.Polyline({
        path: route.path,
        strokeColor: colour,
        strokeWeight: 4,
        strokeOpacity: 0.85,
        zIndex: 50,  // 低于小区轮廓(小区是默认 100+)
      });
      mapInstanceRef.current.add(line);
      transitLinesRef.current.push(line);
    });

    transit.stops.forEach(stop => {
      const dot = new window.AMap.Marker({
        position: [stop.lng, stop.lat],
        anchor: 'center',
        content: `<div style="width:10px;height:10px;border-radius:50%;background:#fff;border:2px solid #3B76D2;box-shadow:0 1px 2px rgba(0,0,0,0.3)"></div>`,
      });
      mapInstanceRef.current.add(dot);
      transitStopsRef.current.push(dot);
    });
  }, [transit, mapLoaded]);

  // 选中小区: 轮廓加粗高亮 + 画 1500m 配套半径圈
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded) return;

    const selId = selectedCommunity?.community_id ?? null;
    for (const [cid, overlay] of polygonByCommIdRef.current) {
      const community = commByCidRef.current.get(cid);
      if (community) overlay.setOptions(styleOptions(community, cid === selId, false));
    }

    if (circleRef.current) {
      map.remove(circleRef.current);
      circleRef.current = null;
    }
    if (selectedCommunity?.latitude && selectedCommunity?.longitude) {
      circleRef.current = new window.AMap.Circle({
        center: [selectedCommunity.longitude, selectedCommunity.latitude],
        radius: 1500,
        strokeColor: '#7C8BA1',
        strokeWeight: 1.2,
        strokeStyle: 'dashed',
        strokeOpacity: 0.75,
        fillColor: '#7C8BA1',
        fillOpacity: 0.05,
        bubble: true,
        zIndex: 5,
      });
      map.add(circleRef.current);
    }
  }, [selectedCommunity, mapLoaded]);

  // 外部触发的飞行定位 (数据看板"查看"): 放大到社区级视野(zoom 16)
  useEffect(() => {
    if (!mapInstanceRef.current || !mapLoaded || !focus) return;
    mapInstanceRef.current.setZoomAndCenter(16, [focus.lng, focus.lat], true); // 立即跳转, 动画在后台标签页会被冻结
  }, [focus, mapLoaded]);

  // 添加 POI 圆点（已跨小区去重, 由 page.tsx 按开关过滤后传入）
  useEffect(() => {
    if (!mapInstanceRef.current || !mapLoaded) return;

    poiMarkersRef.current.forEach(m => mapInstanceRef.current.remove(m));
    poiMarkersRef.current = [];
    poiMarkerStylesRef.current = [];

    const useIcon = mapInstanceRef.current.getZoom() >= POI_ICON_MIN_ZOOM;
    (pois || []).forEach(poi => {
      const color = poi.type === 'school' && poi.level
        ? (SCHOOL_LEVEL_COLORS[poi.level] ?? POI_MARKER_COLORS.school)
        : (POI_MARKER_COLORS[poi.type] || '#AAAAAA');
      const icon = POI_ICONS[poi.type] ?? POI_ICONS.school;
      const dot = buildPOIDotContent(color);
      const full = buildPOIIconContent(color, icon);
      const marker = new window.AMap.Marker({
        position: [poi.longitude, poi.latitude],
        anchor: 'center',
        title: poi.name,
        content: useIcon ? full : dot,
        cursor: 'pointer',
      });
      marker.on('click', () => {
        const info = poiInfoWindowRef.current;
        if (!info) return;
        info.setContent(buildPOIInfoContent(poi, color));
        info.open(mapInstanceRef.current, [poi.longitude, poi.latitude]);
      });
      mapInstanceRef.current.add(marker);
      poiMarkersRef.current.push(marker);
      poiMarkerStylesRef.current.push({ marker, dot, full });
    });
  }, [pois, mapLoaded]);

  // 绘制地铁路线 + 站点 (一次性, OSM 官方颜色)
  useEffect(() => {
    if (!mapInstanceRef.current || !mapLoaded || ! transit) return;

    transitLinesRef.current.forEach(p => mapInstanceRef.current.remove(p));
    transitLinesRef.current = [];
    transitStopsRef.current.forEach(m => mapInstanceRef.current.remove(m));
    transitStopsRef.current = [];

    const newLines: any[] = [];
    const newStops: any[] = [];
    for (const route of transit.routes) {
      const polyline = new window.AMap.Polyline({
        path: route.path,
        strokeColor: route.colour || '#3B76D2',
        strokeWeight: 4,
        strokeOpacity: 0.85,
        zIndex: 1, // 在小区轮廓下方
      });
      polyline.setMap(mapInstanceRef.current);
      polyline.on('mouseover', () => polyline.setOptions({ strokeWeight: 6, strokeOpacity: 1 }));
      polyline.on('mouseout', () => polyline.setOptions({ strokeWeight: 4, strokeOpacity: 0.85 }));
      polyline.on('click', () => {
        poiInfoWindowRef.current?.close();
        poiInfoWindowRef.current?.setContent(
          `<div style="padding:6px 10px;min-width:120px">
            <div style="font-size:14px;font-weight:600;color:#1c2434">${route.name}</div>
            <div style="font-size:12px;color:#5a6478;margin-top:3px;display:flex;align-items:center;gap:6px">
              <span style="width:10px;height:3px;background:${route.colour};display:inline-block"></span>${route.ref}号线
            </div>
          </div>`
        );
        poiInfoWindowRef.current?.open(mapInstanceRef.current, route.path[Math.floor(route.path.length / 2)]);
      });
      newLines.push(polyline);
    }
    for (const stop of transit.stops) {
      const marker = new window.AMap.Marker({
        position: [stop.lng, stop.lat],
        anchor: 'center',
        title: stop.name,
        content: `<div style="width:9px;height:9px;border-radius:50%;background:#3B76D2;border:1.5px solid #fff;box-shadow:0 0 4px rgba(0,0,0,0.5)"></div>`,
      });
      marker.on('click', () => {
        poiInfoWindowRef.current?.close();
        poiInfoWindowRef.current?.setContent(
          `<div style="padding:6px 10px;min-width:120px">
            <div style="font-size:14px;font-weight:600;color:#1c2434">${stop.name}</div>
            <div style="font-size:12px;color:#5a6478;margin-top:3px">地铁站</div>
          </div>`
        );
        poiInfoWindowRef.current?.open(mapInstanceRef.current, [stop.lng, stop.lat]);
      });
      marker.setMap(mapInstanceRef.current);
      newStops.push(marker);
    }
    transitLinesRef.current = newLines;
    transitStopsRef.current = newStops;
  }, [transit, mapLoaded]);

  return (
    <>
      <div
        ref={mapRef}
        style={{
          width: '100%',
          height: '100%',
          position: 'absolute',
          inset: 0,
        }}
      />
      {/* 轮廓悬停提示 (跟随鼠标, 不拦截事件) */}
      <div ref={tooltipRef} className="map-tooltip" />
    </>
  );
}