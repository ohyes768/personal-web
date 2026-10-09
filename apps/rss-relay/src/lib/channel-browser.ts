'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { rssRelayApi } from './api';
import type { Channel } from './types';

export function useChannelBrowser() {
  const [channel, setChannel] = useState('');
  const [showDisabled, setShowDisabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const generation = useRef(0);
  const readUrl = useCallback(() => {
    const query = new URL(window.location.href).searchParams;
    setChannel(query.get('channel') || '');
    setShowDisabled(query.get('show_disabled') === '1');
    setNotice(''); setReady(true);
  }, []);
  useEffect(() => {
    readUrl(); window.addEventListener('popstate', readUrl);
    return () => window.removeEventListener('popstate', readUrl);
  }, [readUrl]);
  const updateUrl = useCallback((id: string, disabled: boolean, replace = false) => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set('channel', id); else url.searchParams.delete('channel');
    if (disabled) url.searchParams.set('show_disabled', '1'); else url.searchParams.delete('show_disabled');
    window.history[replace ? 'replaceState' : 'pushState'](null, '', url);
    setChannel(id); setShowDisabled(disabled);
  }, []);
  const refreshChannels = useCallback(async () => {
    const request = ++generation.current;
    setError('');
    try {
      const response = await rssRelayApi.getChannels(true);
      if (request === generation.current) { setChannels(response.channels); setLoaded(true); }
    } catch (e) {
      if (request === generation.current) { setError(e instanceof Error ? e.message : '加载渠道失败'); setLoaded(false); }
    }
  }, []);
  useEffect(() => { void refreshChannels(); return () => { generation.current++; }; }, [refreshChannels]);
  const active = channels.find(c => c.id === channel);
  useEffect(() => {
    if (!ready || !loaded || !channel) return;
    if (!active) { updateUrl('', showDisabled, true); setNotice('该渠道不存在，已返回全部内容。'); }
    else if (!active.enabled && !showDisabled) updateUrl(channel, true, true);
  }, [ready, loaded, channel, active, showDisabled, updateUrl]);
  return {
    channel, showDisabled, ready, channels, active, loaded, error, notice, refreshChannels,
    choose: (id: string) => { setNotice(''); const target = channels.find(c => c.id === id); updateUrl(id, showDisabled || target?.enabled === false); },
    toggleDisabled: (show: boolean) => updateUrl(!show && active?.enabled === false ? '' : channel, show),
  };
}
