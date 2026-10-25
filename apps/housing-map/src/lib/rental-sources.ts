export interface RentalSource {
  source?: 'fang' | 'xingfuli';
  source_community_id: string;
  source_name: string;
  source_url: string;
  source_address: string | null;
  evidence?: string[];
  notes?: string;
  verified_at?: string;
}
export interface SourceCommunity {
  community_id: string;
  community_name: string;
  community_alias?: string;
  district?: string;
  subdistrict?: string;
  mapping?: RentalSource | null;
  candidate_count?: number;
}
export interface SourceDetail {
  community?: SourceCommunity;
  mapping: RentalSource | null;
  candidates: RentalSource[];
  found_count?: number;
}
export const RENTAL_DATA_CHANGED = 'housing-rental-data-changed';
export function rentalDataChanged() { window.dispatchEvent(new Event(RENTAL_DATA_CHANGED)); }
export function sourcePath(communityId: string) {
  return `/api/map/communities/${encodeURIComponent(communityId)}/rental-source`;
}
export function safeSourceLink(url: string): string | undefined {
  try {
    const parsed = new URL(url);
    const sourceAllowed = ['zu.fang.com', 'hz.zu.fang.com'].includes(parsed.hostname)
      || (parsed.hostname === 'm.xflapp.com'
        && /^\/zufang\/(?:neighbor-house-list\/)?hz-\d+\.html$/.test(parsed.pathname)
        && !parsed.search && !parsed.hash);
    return parsed.protocol === 'https:' && sourceAllowed && !parsed.username && !parsed.password
      && (!parsed.port || parsed.port === '443') ? url : undefined;
  } catch { return undefined; }
}
export async function sourceRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json();
  if (!response.ok || payload.success !== true) {
    throw new Error(typeof payload.detail === 'string' ? payload.detail : '租金来源暂时不可用，请重试');
  }
  return payload.data as T;
}
