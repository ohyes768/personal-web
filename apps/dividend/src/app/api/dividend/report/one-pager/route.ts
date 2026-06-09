import { NextResponse } from 'next/server';

const API_BASE = process.env.BACKEND_URL || 'http://localhost:8092';

export async function GET() {
  try {
    const response = await fetch(`${API_BASE}/api/dividend/report/one-pager`, {
      method: 'GET',
      headers: { 'Accept': 'text/html;charset=utf-8' },
    });

    if (!response.ok) {
      return NextResponse.json({ error: '生成报告失败' }, { status: response.status });
    }

    const blob = await response.blob();
    const arrayBuffer = await blob.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        'Content-Type': 'text/html;charset=utf-8',
        'Content-Disposition': response.headers.get('Content-Disposition') || 'attachment; filename="dividend_report.html"',
      },
    });
  } catch (error) {
    console.error('Failed to fetch report:', error);
    return NextResponse.json({ error: '生成报告失败，请稍后重试' }, { status: 500 });
  }
}