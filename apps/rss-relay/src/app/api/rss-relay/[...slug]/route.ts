/**
 * BFF catch-all：把 /rss/api/rss-relay/<slug> 转发到后端 http://localhost:8095/api/<slug>
 *
 * 后端真实路由：/api/posts、/api/post、/api/rss.xml、/health（无 /api/rss-relay/ 这一层）
 * 例：前端调 /rss/api/rss-relay/posts?limit=50 → 转发到 http://localhost:8095/api/posts?limit=50
 *
 * 为什么路径带 /rss 前缀：Next.js App Router 的 basePath 同时作用于 pages 和 API routes。
 *
 * 生产环境由 nginx 剥前缀（location /api/rss-relay/ { proxy_pass .../api/; }），
 * 前端访问的是 https://web.duomi77.cn:9443/rss/api/rss-relay/...，
 * nginx 会把 /rss 前缀剥掉成 /api/rss-relay/...，然后再剥 /api/ 转给后端。
 * 此 BFF 路由只在本地开发（pnpm dev）时启用。
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8095/api').replace(/\/?$/, '/');

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string[] }> }
) {
  return proxy(request, await params, 'GET');
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string[] }> }
) {
  return proxy(request, await params, 'POST');
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string[] }> }
) {
  return proxy(request, await params, 'DELETE');
}

async function proxy(
  request: NextRequest,
  resolved: { slug: string[] },
  method: string
) {
  try {
    const path = resolved.slug.join('/');
    const targetUrl = new URL(path, BACKEND_URL);
    request.nextUrl.searchParams.forEach((v, k) => {
      targetUrl.searchParams.set(k, v);
    });

    const init: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (method === 'POST' || method === 'PUT') {
      init.body = await request.text();
    }

    const response = await fetch(targetUrl.toString(), init);
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: {
        'Content-Type':
          response.headers.get('Content-Type') || 'application/json',
      },
    });
  } catch (error) {
    console.error('BFF proxy error:', error);
    return Response.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
