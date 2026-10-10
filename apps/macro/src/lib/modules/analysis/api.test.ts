import assert from 'node:assert/strict';
import { test } from 'node:test';
import { EventDecoder, decodeEvent, streamAnalysis } from './api';

test('SSE decoder preserves partial frames, CRLF and heartbeat comments', () => {
  const parser = new EventDecoder();
  assert.deepEqual(parser.push(': heartbeat\r\n\r\ndata: {"kind":"del'), []);
  assert.deepEqual(parser.push('ta","text":"利差"}\r\n\r\ndata: {"kind":"done"}\n\n'), [
    { kind: 'delta', text: '利差' }, { kind: 'done' },
  ]);
  assert.throws(() => decodeEvent({ kind: 'delta', text: 2 }));
});

test('stream decoder handles UTF-8 split across bytes and rejects unfinished response', async () => {
  const original = globalThis.fetch;
  const make = (text: string) => {
    const bytes = new TextEncoder().encode(text);
    return new Response(new ReadableStream({ start(controller) {
      for (let i = 0; i < bytes.length; i += 2) controller.enqueue(bytes.slice(i, i + 2));
      controller.close();
    } }));
  };
  try {
    globalThis.fetch = async () => make('data: {"kind":"delta","text":"中国利差"}\n\ndata: {"kind":"done"}\n\n');
    const events: unknown[] = [];
    await streamAnalysis('session', 'request', 'question', new AbortController().signal, event => events.push(event));
    assert.deepEqual(events, [{ kind: 'delta', text: '中国利差' }, { kind: 'done' }]);
    globalThis.fetch = async () => make('data: {"kind":"delta","text":"partial"}\n\n');
    await assert.rejects(streamAnalysis('s', 'r', 'q', new AbortController().signal, () => {}), /未完成/);
    globalThis.fetch = async () => make('data: {"kind":"error","message":"上游失败"}\n\n');
    await assert.rejects(streamAnalysis('s', 'r', 'q', new AbortController().signal, () => {}), /上游失败/);
  } finally { globalThis.fetch = original; }
});
