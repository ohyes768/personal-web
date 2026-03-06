import { NextRequest, NextResponse } from 'next/server'

const DOUYIN_SERVICE_URL = process.env.DOUYIN_SERVICE_URL || 'http://localhost:8093'

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
      { success: false, error: 'Failed to fetch data from backend service' },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/')
  const url = new URL(request.url)
  const targetUrl = `${DOUYIN_SERVICE_URL}/api/${path}${url.search}`

  return proxyRequest('GET', targetUrl)
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/')
  const body = await request.json()
  const targetUrl = `${DOUYIN_SERVICE_URL}/api/${path}`

  return proxyRequest('POST', targetUrl, {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/')
  const targetUrl = `${DOUYIN_SERVICE_URL}/api/${path}`

  return proxyRequest('DELETE', targetUrl)
}
