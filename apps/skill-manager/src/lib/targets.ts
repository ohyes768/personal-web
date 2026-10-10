export type LinkTargetKey = 'openclaw' | 'hermes';
export type ExportTargetKey = 'windows-codex' | 'windows-claude';
export type TargetKey = LinkTargetKey | ExportTargetKey;

export const TARGETS = {
  openclaw: { kind: 'link', label: 'OpenClaw' },
  hermes: { kind: 'link', label: 'Hermes' },
  'windows-codex': { kind: 'export', label: 'Windows Codex' },
  'windows-claude': { kind: 'export', label: 'Windows Claude Code' },
} as const;

export const LINK_TARGETS: LinkTargetKey[] = ['openclaw', 'hermes'];
export const EXPORT_TARGETS: ExportTargetKey[] = ['windows-codex', 'windows-claude'];
export const TARGET_LABEL: Record<TargetKey, string> = Object.fromEntries(
  Object.entries(TARGETS).map(([key, meta]) => [key, meta.label])
) as Record<TargetKey, string>;
