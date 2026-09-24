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
