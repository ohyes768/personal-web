/**
 * API HTTP 客户端
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

  private async request<T>(url: string, options?: RequestInit): Promise<T> {
    try {
      const response = await fetch(url, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...options?.headers },
      });

      if (!response.ok) {
        // 尝试从响应体中提取后端返回的 detail/message/error 字段
        // 例如 FastAPI 的 HTTPException(429, detail="距上次更新仅 N 天...") 会返回 {"detail": "..."}
        let serverMsg = '';
        try {
          const body = await response.clone().json();
          serverMsg = body.detail || body.message || body.error || '';
        } catch {
          // 响应体不是 JSON 时忽略
        }
        throw new Error(serverMsg || `请求失败 (HTTP ${response.status})`);
      }

      if (this.mode === 'direct') return response.json() as Promise<T>;

      const result: ApiResponse<T> = await response.json();
      if (!result.success) throw new Error(result.error || result.message || 'API request failed');
      return result.data;
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  async get<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    const effectiveBase = this.baseUrl === '/' ? '' : this.baseUrl;
    let url: string;

    if (!effectiveBase || effectiveBase.startsWith('/')) {
      url = `${effectiveBase}${endpoint}`;
      if (params) {
        const validParams = Object.fromEntries(
          Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
        );
        if (Object.keys(validParams).length > 0) {
          url += `?${new URLSearchParams(validParams).toString()}`;
        }
      }
    } else {
      const urlObj = new URL(endpoint, effectiveBase);
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          if (v !== undefined && v !== null && v !== '') urlObj.searchParams.append(k, v);
        });
      }
      url = urlObj.toString();
    }

    return this.request<T>(url);
  }

  async post<T>(endpoint: string, data?: any): Promise<T> {
    const effectiveBase = this.baseUrl === '/' ? '' : this.baseUrl;
    return this.request<T>(`${effectiveBase}${endpoint}`, { method: 'POST', body: JSON.stringify(data) });
  }

  async put<T>(endpoint: string, data?: any): Promise<T> {
    const effectiveBase = this.baseUrl === '/' ? '' : this.baseUrl;
    return this.request<T>(`${effectiveBase}${endpoint}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async delete<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    const effectiveBase = this.baseUrl === '/' ? '' : this.baseUrl;
    let url = `${effectiveBase}${endpoint}`;
    if (params) {
      const validParams = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''));
      if (Object.keys(validParams).length > 0) url += `?${new URLSearchParams(validParams).toString()}`;
    }
    return this.request<T>(url, { method: 'DELETE' });
  }
}

export { ApiClient };
export const apiClient = new ApiClient();
export const directClient = new ApiClient('', 'direct');