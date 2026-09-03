/**
 * /funds 根路径 → /funds/bond（债基/股票 URL 对称化后的兼容重定向，保留 query）
 */
import { redirect } from 'next/navigation';

export default async function RootPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const qs = new URLSearchParams(
    Object.entries(sp).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
  ).toString();
  // redirect 路径相对 basePath：/bond → /funds/bond
  redirect(`/bond${qs ? `?${qs}` : ''}`);
}
