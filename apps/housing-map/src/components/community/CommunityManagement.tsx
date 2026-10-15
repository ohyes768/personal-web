'use client';

import CommunityWorkspace from './DirectoryFlowWorkspace';
export { DirectorySourceCard, ResidentialStateBadge, safeDirectoryLink, AdmissionControls } from './DirectoryCards';

export default function CommunityManagement({ onChanged, initialSource = '' }: { onChanged: () => void; initialSource?: string }) {
  return <CommunityWorkspace onChanged={onChanged} initialSource={initialSource} />;
}
