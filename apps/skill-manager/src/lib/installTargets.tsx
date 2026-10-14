'use client';
import { createContext, useContext } from 'react';
import type { LinkTargetKey } from './targets';

export interface InstallTarget {
  id: LinkTargetKey;
  provider: 'hermes';
  profile_name: string;
  name: string;
  install_path: string;
  configured: boolean;
  available: boolean;
  unavailable_reason: string;
}
export const InstallTargetsContext = createContext<{
  current: LinkTargetKey; targets: InstallTarget[]; error: string; loading: boolean;
}>({ current: 'hermes', targets: [], error: '', loading: false });
export const useInstallTargets = () => useContext(InstallTargetsContext);
export const installTargetLabel = (targets: InstallTarget[], id: string) => targets.find(t => t.id === id)?.name ?? (id === 'hermes' ? 'Hermes' : id);
