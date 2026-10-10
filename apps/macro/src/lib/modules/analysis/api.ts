/** Single owner of the analysis HTTP/SSE boundary. */
export interface ChartDefinition { id: string; title: string; description: string; series_ids: string[]; series: { id: string; label: string; unit: string }[]; version: string }
export interface EvidenceSeries {
  evidence_id: string; label: string; unit: string; derived: boolean; status: string;
  statistics: null | { start: { date: string; value: number }; end: { date: string; value: number }; change_bp: number | null; count: number };
}
export interface Snapshot {
  chart_id: string; title: string; snapshot_id: string; range: [string, string]; generated_at: string;
  primary: EvidenceSeries[]; derived: EvidenceSeries[]; references: EvidenceSeries[]; quality: string;
}
export interface AnalysisSession { session_id: string; snapshot: Snapshot; expires_in: number }
export interface AuthStatus { unlocked: boolean; configured: boolean; model_ready: boolean }
export type StreamEvent = { kind: 'delta'; text: string } | { kind: 'done' } | { kind: 'error'; message: string } | { kind: 'meta' };
const ROOT = '/api/macro/analysis';

export class AnalysisError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
async function checked(response: Response) {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new AnalysisError(typeof body?.detail === 'string' ? body.detail : `分析请求失败 (${response.status})`, response.status);
  }
  return response;
}
export async function analysisRequest<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await checked(await fetch(ROOT + path, {
    method, credentials: 'same-origin', cache: 'no-store', signal,
    ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  }));
  return response.json();
}
export function decodeEvent(value: unknown): StreamEvent {
  if (!value || typeof value !== 'object' || !('kind' in value)) throw new Error('无效的分析响应');
  if (value.kind === 'delta' && 'text' in value && typeof value.text === 'string') return { kind: 'delta', text: value.text };
  if (value.kind === 'error' && 'message' in value && typeof value.message === 'string') return { kind: 'error', message: value.message };
  if (value.kind === 'done' || value.kind === 'meta') return { kind: value.kind };
  throw new Error('无法识别的分析响应');
}
/** Handles arbitrary byte boundaries and CRLF without duplicating parsers in components. */
export class EventDecoder {
  private pending = '';
  push(text: string): StreamEvent[] {
    this.pending += text;
    const events: StreamEvent[] = [];
    let match: RegExpExecArray | null;
    while ((match = /\r?\n\r?\n/.exec(this.pending))) {
      const block = this.pending.slice(0, match.index);
      this.pending = this.pending.slice(match.index + match[0].length);
      const payload = block.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
      if (payload) events.push(decodeEvent(JSON.parse(payload)));
    }
    return events;
  }
}
export async function streamAnalysis(sessionId: string, requestId: string, message: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void) {
  const response = await checked(await fetch(`${ROOT}/sessions/${sessionId}/messages`, {
    method: 'POST', credentials: 'same-origin', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request_id: requestId, message }),
  }));
  if (!response.body) throw new Error('浏览器无法读取分析流');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new EventDecoder();
  let complete = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      const text = decoder.decode(value, { stream: !done });
      for (const event of parser.push(text)) {
        if (event.kind === 'done') complete = true;
        if (event.kind === 'error') throw new Error(event.message);
        onEvent(event);
      }
      if (done) break;
    }
    if (!complete) throw new Error('连接中断，回答未完成');
  } finally { reader.releaseLock(); }
}
