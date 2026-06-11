/**
 * API 代理路由
 * 将前端 API 请求转发到后端服务
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8092';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const requestUrl = new URL(request.url);
    const apiPath = requestUrl.pathname.replace(/^\/api\/dividend\//, '/');
    const targetUrl = new URL(apiPath, BACKEND_URL);

    requestUrl.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value);
    });

    const response = await fetch(targetUrl.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
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
    const requestUrl = new URL(request.url);
    const apiPath = requestUrl.pathname.replace(/^\/api\/dividend\//, '/');
    const targetUrl = new URL(apiPath, BACKEND_URL);
    const body = await request.json();

    const response = await fetch(targetUrl.toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
    const requestUrl = new URL(request.url);
    const apiPath = requestUrl.pathname.replace(/^\/api\/dividend\//, '/');
    const targetUrl = new URL(apiPath, BACKEND_URL);

    requestUrl.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value);
    });

    const response = await fetch(targetUrl.toString(), {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
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