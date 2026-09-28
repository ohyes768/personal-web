/** 展示格式化工具：Skill 卡片副标题与时间在管理/部署两处看板共用。 */

/** 仓库 URL 缩短为 owner/repo；非 GitHub 地址原样返回。 */
export function shortRepo(repository: string): string {
  return repository.replace(/^https?:\/\/github\.com\//i, '').replace(/\/+$/, '');
}

/** ISO 时间转本地可读（无效值原样返回）。 */
export function formatPublishedAt(value: string): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('zh-CN', { hour12: false });
}

/** 秒数转 M:SS（扫描/后台任务已用时计时）。 */
export function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/** git 进度行尾明细清洗：去掉前导 "|" 与尾缀 ", done."，如
 * "| 22.27 KiB | 1.39 MiB/s, done." → "22.27 KiB | 1.39 MiB/s"。 */
export function formatProgressDetail(detail: string): string {
  return detail
    .replace(/^\|/, '')
    .replace(/,\s*done\.?$/, '')
    .trim();
}

/** GitHub 任务 stage → 界面文案（task_manager 的 stage 取值，design §2）。 */
export function taskStageLabel(stage: string): string {
  const labels: Record<string, string> = {
    remote_check: '检查远端仓库',
    negotiating: '协商传输',
    receiving: '克隆中',
    resolving: '解析增量',
    discover: '扫描候选目录',
    registry: '写入登记',
  };
  return labels[stage] ?? stage;
}
