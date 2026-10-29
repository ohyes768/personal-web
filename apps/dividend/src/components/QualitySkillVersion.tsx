/** Stored provenance is independent of the currently installed version. */
export function QualitySkillVersion({ version, currentVersion }: { version?: string | null; currentVersion?: string | null }) {
  const needsReanalysis = !!currentVersion && version !== currentVersion;
  return <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
    <span className="font-mono text-ink-muted">{version ? `v${version}` : '版本未知'}</span>
    {needsReanalysis && <span className="text-amber-700" title={`当前已部署版本 v${currentVersion}；${version ? '该评分使用其他版本' : '该评分未记录版本'}，建议重新分析`}>需重评</span>}
  </span>;
}
