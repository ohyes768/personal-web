/**
 * fund-flow API catch-all 代理
 * 阶段二：apps/fund-flow 拆离 monorepo
 * 将前端 /api/fund-flow/* 请求转发到 global-macro-fin 后端
 */
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.MACRO_SERVICE_URL || 'http://localhost:8094';

async function proxyRequest(
  method: string,
  url: string,
  options?: RequestInit
): Promise<NextResponse> {
  try {
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
    console.error('API proxy error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params;
  const path = resolvedParams.path.join('/');
  const targetUrl = new URL(`/api/fund-flow/${path}`, BACKEND_URL);
  request.nextUrl.searchParams.forEach((value, key) => {
    targetUrl.searchParams.set(key, value);
  });
  return proxyRequest('GET', targetUrl.toString());
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params;
  const path = resolvedParams.path.join('/');
  const targetUrl = new URL(`/api/fund-flow/${path}`, BACKEND_URL);
  const body = await request.text();
  return proxyRequest('POST', targetUrl.toString(), { body, headers: { 'Content-Type': 'application/json' } });
}
