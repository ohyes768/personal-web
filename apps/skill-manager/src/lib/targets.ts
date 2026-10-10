export type LinkTargetKey = 'openclaw' | 'hermes';
import type { ExportTarget } from './types';
export type ExportTargetKey = string;
export type TargetKey = LinkTargetKey;

export const TARGETS = {
  openclaw: { kind: 'link', label: 'OpenClaw' },
  hermes: { kind: 'link', label: 'Hermes' },
} as const;

export const LINK_TARGETS: LinkTargetKey[] = ['openclaw', 'hermes'];
// HTML pattern uses the Unicode v flag; a literal hyphen must be escaped.
export const EXPORT_TARGET_ID_PATTERN = '[a-z0-9][a-z0-9\\-]{0,62}';
export const TARGET_LABEL: Record<TargetKey, string> = Object.fromEntries(
  Object.entries(TARGETS).map(([key, meta]) => [key, meta.label])
) as Record<TargetKey, string>;

export const enabledExportTargets = (targets: ExportTarget[]) => targets.filter((target) => target.enabled);
export const exportTargetLabel = (targets: ExportTarget[], id: string) => targets.find((target) => target.id === id)?.name ?? id;
export function selectedExportTarget(targets: ExportTarget[], initial?: string): string {
  const enabled = enabledExportTargets(targets);
  return enabled.find((target) => target.id === initial)?.id ?? enabled[0]?.id ?? '';
}
