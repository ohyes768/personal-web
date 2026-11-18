/**
 * 债基·市场 tab 旧路由（/funds/discovery-bond）→ 合并页 redirect
 *
 * 11-15-source-segmented：采集入口收敛为「债基」页 + 来源分段控件，
 * 本路由保留为 redirect（收藏兼容）；?source=market 落到新页的市场态。
 */
import { redirect } from 'next/navigation';

export default async function DiscoveryBondRedirectPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(sp)) {
    if (typeof v === 'string' && v !== '') params.set(k, v);
    else if (Array.isArray(v) && v.length > 0) params.set(k, v[0]);
  }
  params.set('source', 'market');
  redirect(`/bond?${params.toString()}`);
}
