/**
 * 股息率 API 路由代理
 * 解决跨域问题，将请求转发到后端 FastAPI 服务
 */
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.DIVIDEND_API_URL || 'http://localhost:8092';

async function proxyRequest(
  method: string,
  url: string,
  options?: RequestInit
): Promise<NextResponse> {
  try {
    console.log(`[API Proxy] Request: ${method} ${url}`);
    const response = await fetch(url, {
      method,
      ...options,
    });

    const contentType = response.headers.get('content-type');
    let data: any;

    if (contentType?.includes('application/json')) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`[API Proxy] ${method} ${url} failed:`, error);
    return NextResponse.json(
      { error: 'Failed to fetch data from backend service' },
      { status: 500 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const url = new URL(request.url);
  // 去掉 'dividend' 前缀，直接拼接路径
  const targetUrl = `${BACKEND_URL}/api/${path.filter(p => p !== 'dividend').join('/')}${url.search}`;

  return proxyRequest('GET', targetUrl);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const url = new URL(request.url);
  const targetUrl = `${BACKEND_URL}/api/${path.filter(p => p !== 'dividend').join('/')}${url.search}`;

  // 获取请求体
  const body = await request.json();

  return proxyRequest('POST', targetUrl, {
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
}