/**
 * API HTTP 客户端
 * 复制自 packages/api-client/src/client.ts + types.ts（精简版）
 * 阶段二：apps/economic 拆离 monorepo
 */

export interface ApiResponse<T = any> {
  success: boolean;
  data: T;
  message?: string;
  error?: string;
}

type ApiClientMode = 'wrapped' | 'direct';

class ApiClient {
  private baseUrl: string;
  private mode: ApiClientMode;

  constructor(baseUrl: string = '', mode: ApiClientMode = 'wrapped') {
    this.baseUrl = baseUrl || process.env.NEXT_PUBLIC_API_BASE_URL || '';
    this.mode = mode;
  }

  private async request<T>(
    url: string,
    options?: RequestInit
  ): Promise<T> {
    try {
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

      if (this.mode === 'direct') {
        return response.json() as Promise<T>;
      }

      const result: ApiResponse<T> = await response.json();

      if (!result.success) {
        throw new Error(result.error || result.message || 'API request failed');
      }

      return result.data;
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  async get<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    const isRelativePath = !this.baseUrl || this.baseUrl.startsWith('/');

    let url: string;
    if (isRelativePath) {
      url = `${this.baseUrl}${endpoint}`;
      if (params) {
        const validParams = Object.fromEntries(
          Object.entries(params).filter(([_, value]) => value !== undefined && value !== null && value !== '')
        );
        const searchParams = new URLSearchParams(validParams);
        url += `?${searchParams.toString()}`;
      }
    } else {
      const urlObj = new URL(endpoint, this.baseUrl);
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined && value !== null && value !== '') {
            urlObj.searchParams.append(key, value);
          }
        });
      }
      url = urlObj.toString();
    }

    return this.request<T>(url);
  }

  async post<T>(endpoint: string, data?: any): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    // 用 {} 兜底避免 body=undefined 时 fetch 发送空 POST body 引发下游 JSON parse 失败
    return this.request<T>(url, {
      method: 'POST',
      body: JSON.stringify(data ?? {}),
    });
  }

  async put<T>(endpoint: string, data?: any): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    return this.request<T>(url, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async delete<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    let url = `${this.baseUrl}${endpoint}`;
    if (params) {
      const searchParams = new URLSearchParams(params);
      url += `?${searchParams.toString()}`;
    }
    return this.request<T>(url, {
      method: 'DELETE',
    });
  }
}

export { ApiClient };
export const apiClient = new ApiClient();
export const directClient = new ApiClient('', 'direct');
