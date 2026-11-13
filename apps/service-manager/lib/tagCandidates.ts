/** 候选标签：全库标签并集 ∪ 本条已有 ∪ 当前勾选，去重排序。 */

export function getTagCandidates(
  allTags: string[],
  ownTags: string[],
  selected: string[],
): string[] {
  return Array.from(new Set([...allTags, ...ownTags, ...selected])).sort();
}
