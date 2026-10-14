import { afterEach, describe, expect, it, vi } from 'vitest';
import { downloadCollection, exportSkill } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('ZIP downloads', () => {
  function setup() {
    vi.useFakeTimers();
    const anchor = { href: '', download: '', click: vi.fn(), remove: vi.fn() };
    const appendChild = vi.fn();
    vi.stubGlobal('document', { createElement: () => anchor, body: { appendChild } });
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:collection');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const fetch = vi.fn().mockResolvedValue(new Response(new Blob(['zip']), {
      headers: { 'Content-Disposition': 'attachment; filename="owner__repo-collection-abc.zip"' },
    }));
    vi.stubGlobal('fetch', fetch);
    return { anchor, fetch, appendChild, revoke };
  }

  it('downloads a repository archive without selected IDs or an export target', async () => {
    const { anchor, fetch, appendChild, revoke } = setup();
    await downloadCollection('member-id');
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/skills/member-id/collection/download');
    expect(anchor.download).toBe('owner__repo-collection-abc.zip');
    expect(anchor.href).toBe('blob:collection');
    expect(appendChild).toHaveBeenCalledWith(anchor);
    expect(anchor.click).toHaveBeenCalledOnce();
    expect(anchor.remove).toHaveBeenCalledOnce();
    vi.runAllTimers();
    expect(revoke).toHaveBeenCalledWith('blob:collection');
  });

  it('reports a missing cache without starting a download', async () => {
    const { anchor, fetch } = setup();
    fetch.mockResolvedValue(new Response(JSON.stringify({ code: 'cache_missing_export', message: '请先恢复仓库缓存' }), { status: 400 }));
    await expect(downloadCollection('member-id')).rejects.toMatchObject({ code: 'cache_missing_export', message: '请先恢复仓库缓存' });
    expect(anchor.click).not.toHaveBeenCalled();
  });

  it('keeps single-skill exports scoped to their target and endpoint', async () => {
    const { fetch, anchor } = setup();
    fetch.mockResolvedValue(new Response(new Blob(['zip'])));
    await exportSkill('member-id', 'windows-codex');
    expect(fetch).toHaveBeenCalledWith('/api/skills/member-id/export', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ target: 'windows-codex' }),
    }));
    expect(anchor.download).toBe('member-id.zip');
  });
});
