/**
 * API HTTP 客户端
 */
import type { ApiResponse } from './types';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080';
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
    // 检测是否是相对路径（以 / 开头，没有协议）
    const isRelativePath = this.baseUrl.startsWith('/');

    let url: string;
    if (isRelativePath) {
      // 相对路径：直接拼接
      url = `${this.baseUrl}${endpoint}`;
      if (params) {
        const searchParams = new URLSearchParams(params);
        url += `?${searchParams.toString()}`;
      }
    } else {
      // 完整 URL：使用 URL 构造函数
      const urlObj = new URL(endpoint, this.baseUrl);
      if (params) {
        Object.keys(params).forEach(key => urlObj.searchParams.append(key, params[key]));
      }
      url = urlObj.pathname + urlObj.search;
    }

    return this.request<T>(url);
  }

  async post<T>(endpoint: string, data?: any): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    return this.request<T>(url, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async put<T>(endpoint: string, data?: any): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    return this.request<T>(url, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async delete<T>(endpoint: string): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    return this.request<T>(url, {
      method: 'DELETE',
    });
  }
}

export const apiClient = new ApiClient();
