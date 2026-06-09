/**
 * API 代理路由
 * 将前端 API 请求转发到后端服务
 */
import { NextRequest } from 'next/server';

// 修复：原 BACKEND_URL='http://localhost:8093/api' 拼出来是 '/api/aweme/{id}' 前缀正确，
// 但当 douyin catch-all 也用同一个 env 时会产生冲突；env var 拆分为 AWEME_BACKEND_URL
// 同时默认值补全 /api/aweme 路径前缀，与后端 router 注册路径对齐
const BACKEND_URL = process.env.AWEME_BACKEND_URL || 'http://localhost:8093/api/aweme';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const resolvedParams = await params;
    const path = resolvedParams.path.join('/');
    const url = new URL(request.url);
    const targetUrl = new URL(path, BACKEND_URL);

    // 复制查询参数
    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value);
    });

    const response = await fetch(targetUrl.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();
    return Response.json(data, { status: response.status });
  } catch (error) {
    console.error('API proxy error:', error);
    return Response.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const resolvedParams = await params;
    const path = resolvedParams.path.join('/');
    const targetUrl = new URL(path, BACKEND_URL);
    const body = await request.json();

    const response = await fetch(targetUrl.toString(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();
    return Response.json(data, { status: response.status });
  } catch (error) {
    console.error('API proxy error:', error);
    return Response.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const resolvedParams = await params;
    const path = resolvedParams.path.join('/');
    const targetUrl = new URL(path, BACKEND_URL);
    const url = new URL(request.url);

    // 复制查询参数
    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value);
    });

    const response = await fetch(targetUrl.toString(), {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (response.status === 204) {
      return new Response(null, { status: 204 });
    }

    const data = await response.json();
    return Response.json(data, { status: response.status });
  } catch (error) {
    console.error('API proxy error:', error);
    return Response.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
