/**
 * API 代理路由
 * 将前端 API 请求转发到后端服务
 */
import { NextRequest } from 'next/server';

// 修复：原默认值 'http://localhost:8080' 8080 是老 gateway 端口（已废弃）
// 改为指向实际后端 douyin-backend 8093 的 /api/ 路径
// （后端真实路由是 /api/videos、/api/aweme/...、/api/stats，没有 /api/douyin/ 这一层）
// path = params.path.join('/')，例 'videos' → 拼成 http://localhost:8093/api/videos
const BACKEND_URL = (process.env.DOUYIN_BACKEND_URL || 'http://localhost:8093/api').replace(/\/?$/, '/');

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