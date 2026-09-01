/**
 * catch-all 代理：/funds/api/funds/* → 后端 :8095/api/funds/*
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8095';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const url = new URL(request.url);
  const target = `${BACKEND_URL}/api/funds/${path.join('/')}${url.search}`;

  try {
    const res = await fetch(target, { cache: 'no-store' });
    const body = await res.arrayBuffer();  // 二进制透传，保住 CSV 的 UTF-8 BOM
    return new Response(body, {
      status: res.status,
      headers: {
        'Content-Type': res.headers.get('Content-Type') || 'application/json',
        ...(res.headers.get('content-disposition')
          ? { 'Content-Disposition': res.headers.get('content-disposition')! }
          : {}),
      },
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : 'proxy error';
    return new Response(JSON.stringify({ detail: `后端不可达: ${message}` }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
