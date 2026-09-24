export function getTagCandidates(allTags: string[], skillTags: string[], selected: string[]): string[] {
  return Array.from(new Set([...allTags, ...skillTags, ...selected])).sort();
}
