/**
 * 全局收尾：把测试期间造的台账条目清干净。
 *
 * 用例自己的 afterEach 清理在**用例超时**时可能来不及跑（超时会把剩余时间吃光），
 * 那些条目就会留在台账里。这里在整轮跑完后按名字前缀兜底清一次。
 * 认证由 nginx basic auth 承担，本地 e2e 直连时无认证。
 */
export default async function globalTeardown() {
  const baseURL = process.env.SM_E2E_BASE_URL || "http://127.0.0.1:3012";
  const origin = new URL(baseURL).origin;

  try {
    const listed = await fetch(`${origin}/api/services/services?page_size=100`);
    if (!listed.ok) return;
    const data = (await listed.json()) as { items?: { id: string; name: string }[] };
    for (const item of data.items ?? []) {
      if (!item.name.startsWith("e2e-")) continue;
      await fetch(`${origin}/api/services/services/${item.id}`, {
        method: "DELETE",
        headers: { Origin: origin },
      });
    }
  } catch {
    // 收尾失败不阻塞测试结果
  }
}
