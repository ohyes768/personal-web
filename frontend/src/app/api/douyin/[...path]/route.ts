import { NextRequest, NextResponse } from 'next/server'

const DOUYIN_SERVICE_URL = process.env.DOUYIN_SERVICE_URL ?? 'http://localhost:8093'

async function proxyRequest(
  method: string,
  url: string,
  options?: RequestInit
): Promise<NextResponse> {
  try {
    const response = await fetch(url, {
      method,
      ...options,
    })

    const contentType = response.headers.get('content-type')
    let data: any

    if (contentType?.includes('application/json')) {
      data = await response.json()
    } else {
      data = await response.text()
    }

    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error(`[API Proxy] ${method} ${url} failed:`, error)
    return NextResponse.json(
      { success: false, error: 'Failed to fetch data from backend service', details: String(error) },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const url = new URL(request.url)
  const targetUrl = `${DOUYIN_SERVICE_URL}/api/${path.join('/')}${url.search}`

  return proxyRequest('GET', targetUrl)
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const targetUrl = `${DOUYIN_SERVICE_URL}/api/${path.join('/')}`

  // 检查请求是否有 body
  const contentType = request.headers.get('content-type')
  let body: string | undefined

  if (contentType?.includes('application/json')) {
    try {
      body = JSON.stringify(await request.json())
    } catch {
      // 没有 body，跳过
    }
  }

  const options: RequestInit = { method: 'POST' }
  if (body) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = body
  }

  return proxyRequest('POST', targetUrl, options)
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const targetUrl = `${DOUYIN_SERVICE_URL}/api/${path.join('/')}`

  return proxyRequest('DELETE', targetUrl)
}
