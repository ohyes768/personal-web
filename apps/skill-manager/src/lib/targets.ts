export type LinkTargetKey = 'hermes' | `hermes:profile:${string}`;
export const isInstallTarget = (id: string) => id === 'hermes' || id.startsWith('hermes:profile:');
import type { ExportTarget } from './types';
export type ExportTargetKey = string;
export type TargetKey = LinkTargetKey;

// HTML pattern uses the Unicode v flag; a literal hyphen must be escaped.
export const EXPORT_TARGET_ID_PATTERN = '[a-z0-9][a-z0-9\\-]{0,62}';
export const enabledExportTargets = (targets: ExportTarget[]) => targets.filter((target) => target.enabled);
export const exportTargetLabel = (targets: ExportTarget[], id: string) => targets.find((target) => target.id === id)?.name ?? id;
export function selectedExportTarget(targets: ExportTarget[], initial?: string): string {
  const enabled = enabledExportTargets(targets);
  return enabled.find((target) => target.id === initial)?.id ?? enabled[0]?.id ?? '';
}
