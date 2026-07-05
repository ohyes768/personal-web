/**
 * API HTTP 客户端（direct 模式）
 * 复制自 apps/douyin/src/lib/api-client.ts，去掉 wrapped 模式（rss-relay 后端不走 {success, data} 包裹）
 */

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = '') {
    // 空串 = 走相对路径（BFF catch-all 或 nginx 代理）
    this.baseUrl = baseUrl || process.env.NEXT_PUBLIC_API_BASE_URL || '';
  }

  private async request<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json() as Promise<T>;
  }

  async get<T>(endpoint: string, params?: Record<string, string | number>): Promise<T> {
    const isRelativePath = !this.baseUrl || this.baseUrl.startsWith('/');

    let url: string;
    if (isRelativePath) {
      url = `${this.baseUrl}${endpoint}`;
      if (params) {
        const validParams = Object.fromEntries(
          Object.entries(params).filter(
            ([_, v]) => v !== undefined && v !== null && v !== ''
          ) as [string, string][]
        );
        const searchParams = new URLSearchParams(validParams);
        const qs = searchParams.toString();
        if (qs) url += `?${qs}`;
      }
    } else {
      const urlObj = new URL(endpoint, this.baseUrl);
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          if (v !== undefined && v !== null && v !== '') {
            urlObj.searchParams.append(k, String(v));
          }
        });
      }
      url = urlObj.toString();
    }

    return this.request<T>(url);
  }
}

export { ApiClient };
export const directClient = new ApiClient();
