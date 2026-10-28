'use client';

import CommunityWorkspace from './DirectoryFlowWorkspace';
export { DirectorySourceCard, ResidentialStateBadge, safeDirectoryLink, AdmissionControls } from './DirectoryCards';

// 定位核对入口: 从地图侧"去核对定位"跳转过来时, 直接打开该小区的定位面板
export interface PositionFocusRequest {
  communityId: string;
  key: number;
}

export default function CommunityManagement({
  onChanged,
  initialSource = '',
  focusPosition = null,
}: {
  onChanged: () => void;
  initialSource?: string;
  focusPosition?: PositionFocusRequest | null;
}) {
  return <CommunityWorkspace onChanged={onChanged} initialSource={initialSource} focusPosition={focusPosition} />;
}
