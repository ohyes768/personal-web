// 新房项目点的标记内容构建: 纯函数, 地图图层与单元测试共用。
//
// 新房没有可靠的建筑聚类轮廓, 也不参与二手价格色阶, 所以用固定类别色 +
// 「新」字徽标表达房源类型; 位置是否核验用实心/空心区分, 不用颜色以外的信息暗示。

import type { Community } from '@/lib/types';

// 新房固定类别色: 深紫, 与二手房价格色阶(绿→黄→橙→红)明显区分, 浅色底图上也可读
export const NEW_HOUSE_COLOR = '#4B3FA8';

// 放大到此级别才显示项目名; 更低时只留「新」徽标, 避免密集时文字堆叠
export const NEW_HOUSE_LABEL_MIN_ZOOM = 13;

// 标记内容是 HTML 字符串, 小区名/项目名需要转义后再拼进去
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch] ?? ch
  ));
}

// 标记文字: 优先用项目名, 没有项目资料时退回小区名(总比空白强)
export function newHouseLabel(community: Community): string {
  const projectName = community.project?.project_name;
  if (projectName && projectName.trim()) return projectName.trim();
  return community.community_name;
}

export interface NewHouseMarkerOptions {
  name: string;
  verified: boolean;  // true=位置已核验(实心), false=待核验(空心)
  selected: boolean;
  showName: boolean;  // 低缩放时只显示「新」徽标
}

/**
 * 新房项目点的标记 HTML。
 * 实心/空心表示位置核验状态, 选中时加一圈高亮环 —— 颜色之外还有形状与文字差异,
 * 不让「深紫 = 新房」成为唯一可辨识线索。
 */
export function buildNewHouseMarkerContent(options: NewHouseMarkerOptions): string {
  const { name, verified, selected, showName } = options;
  const label = escapeHtml(name);
  // 已核验=实心色块, 待核验=白底虚线边, 空心比单纯的颜色差异更容易辨认
  const badgeText = verified
    ? `<span style="font-size:11px;font-weight:700;line-height:16px;padding:0 5px;border-radius:999px;white-space:nowrap;background:${NEW_HOUSE_COLOR};color:#fff;">新</span>`
    : `<span style="font-size:11px;font-weight:700;line-height:16px;padding:0 5px;border-radius:999px;white-space:nowrap;background:#fff;color:${NEW_HOUSE_COLOR};border:1.5px dashed ${NEW_HOUSE_COLOR};">新</span>`;
  const shadow = selected
    ? 'box-shadow:0 0 0 3px rgba(75,63,168,0.35),0 1px 4px rgba(0,0,0,0.35);'
    : 'box-shadow:0 1px 4px rgba(0,0,0,0.35);';

  const body = showName
    ? `<div style="display:flex;align-items:center;gap:4px;padding:1px 8px 1px 3px;border-radius:999px;background:#fff;border:1.5px solid ${NEW_HOUSE_COLOR};${shadow}">`
      + `<span style="display:inline-flex;align-items:center;justify-content:center;border-radius:999px;">${badgeText}</span>`
      + `<span style="font-size:12px;font-weight:600;color:#1c2434;white-space:nowrap;">${label}</span></div>`
    : `<div style="display:inline-flex;align-items:center;justify-content:center;padding:1px;border-radius:999px;background:#fff;border:1.5px solid ${NEW_HOUSE_COLOR};${shadow}">${badgeText}</div>`;

  // 三角指针压住坐标点, 让"点在哪"和"点叫什么"在视觉上分开
  const pointer = `<div style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid ${NEW_HOUSE_COLOR};"></div>`;
  return `<div style="display:flex;flex-direction:column;align-items:center;">${body}${pointer}</div>`;
}
