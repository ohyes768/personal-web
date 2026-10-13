export type AuctionPeriod = '12m' | '24m' | 'all';
export type AuctionAreaBand = 'all' | 'lt90' | '90to144' | 'gte144';
export interface AuctionRound {
  source: string;
  auction_id: string;
  asset_id?: string | null;
  title: string;
  area_m2: number | null;
  area_source?: string | null;
  round: number | null;
  status: string;
  deal_price_yuan: number | null;
  start_price_yuan?: number | null;
  deal_unit_price: number | null;
  end_at: string | null;
  captured_at?: string;
  risk_notes?: Record<string, string>;
  source_url?: string | null;
  original_url?: string | null;
  identity_warning?: string | null;
}
export interface AuctionRecord extends AuctionRound {
  rounds: AuctionRound[];
}
export interface AuctionHistory {
  available: boolean;
  last_run: { complete: boolean; finished_at: string } | null;
  source: string;
  as_of: string;
  stats: {
    deal_property_count: number;
    unit_price_sample_count: number;
    median_unit_price_yuan: number | null;
    min_unit_price_yuan: number | null;
    max_unit_price_yuan: number | null;
    latest_end_at: string | null;
    sample_warning: string | null;
  };
  records: AuctionRecord[];
  total: number;
  page: number;
  page_size: number;
}
export interface AuctionSummary {
  available: boolean;
  counts: Record<string, number>;
}
export interface AuctionListRecord extends AuctionRound {
  address?: string | null;
  start_at?: string | null;
  appraisal_price_yuan?: number | null;
  community_name?: string | null;
  community_id: string | null;
  community_display_name: string | null;
  association_status: 'matched' | 'unmatched';
  source_status?: string;
}
export interface AuctionListData {
  available: boolean;
  records: AuctionListRecord[];
  overall_total: number;
  total: number;
  page: number;
  page_size: number;
  last_run: { complete: boolean; finished_at: string } | null;
}
export async function fetchAuctionData<T>(path: string, signal?: AbortSignal, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/map/${path}`, { ...options, signal });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '法拍数据暂时不可用');
  if (!payload.success || !('data' in payload)) throw new Error('法拍数据响应异常');
  return payload.data;
}
