import { NextRequest, NextResponse } from 'next/server'

const MACRO_SERVICE_URL = process.env.MACRO_SERVICE_URL || 'http://localhost:8094'

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

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const url = new URL(request.url)
  const targetUrl = `${MACRO_SERVICE_URL}/api/macro/${path.join('/')}${url.search}`

  return proxyRequest('GET', targetUrl)
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const body = await request.json()
  const targetUrl = `${MACRO_SERVICE_URL}/api/macro/${path.join('/')}`

  return proxyRequest('POST', targetUrl, {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
