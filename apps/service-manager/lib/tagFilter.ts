/** 标签筛选：多选是 AND —— 同时具备全部选中标签才算命中（与 skill-manager 一致）。 */

export function matchesTags(itemTags: string[], selected: string[]): boolean {
  return selected.every((tag) => itemTags.includes(tag));
}
