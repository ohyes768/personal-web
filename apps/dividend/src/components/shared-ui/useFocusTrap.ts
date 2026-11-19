/**
 * useFocusTrap — 弹层焦点迁入 + 焦点圈（Tab 循环）+ 关闭时焦点归还。
 * Modal 与数据更新抽屉共用，保证同一套键盘行为。
 *
 * active：弹层是否打开。
 * scopeRef：焦点圈范围（弹层内容本体；遮罩不进 Tab 序列——aria-modal 已把读屏上下文圈在弹层内，
 *   焦点落在遮罩上读屏用户听不到内容）。
 * layerIdRef：modal-stack 的层 id（pushLayer 的结果存 ref）。**事件时**读 .current：
 *   本 hook 的 effect 可能先于入栈 effect 执行，读 ref 而非 effect 参数可避开顺序问题。
 *   有层叠在本层之上时不拦截 Tab，让顶层弹层自己管焦点；顶层关闭归还焦点后自然落回本层范围。
 */
'use client';

import { useEffect, type RefObject } from 'react';
import { hasLayerOnTop } from '@/lib/modal-stack';

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useFocusTrap<T extends HTMLElement>(
  active: boolean,
  scopeRef: RefObject<T | null>,
  layerIdRef: RefObject<symbol | null>,
) {
  useEffect(() => {
    if (!active) return;

    // 打开前的触发元素：关闭后焦点归还，读屏/键盘用户不丢失上下文
    const lastFocused = (document.activeElement as HTMLElement | null) ?? null;
    const scope = scopeRef.current;
    if (!scope) return;

    const getFocusable = () => [...scope.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)];

    // 迁入本层首个可聚焦元素（一般是标题栏的「关闭」按钮）
    const t = window.setTimeout(() => {
      const list = getFocusable();
      (list[0] ?? scope)?.focus();
    }, 0);

    const trapTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const layerId = layerIdRef.current;
      if (!layerId || hasLayerOnTop(layerId)) return; // 有层叠在上面，焦点归它管
      const list = getFocusable();
      if (list.length === 0) { e.preventDefault(); return; }
      const first = list[0];
      const last = list[list.length - 1];
      const activeEl = document.activeElement as HTMLElement | null;
      if (e.shiftKey) {
        if (activeEl === first || !scope.contains(activeEl)) { e.preventDefault(); last.focus(); }
      } else if (activeEl === last || !scope.contains(activeEl)) {
        e.preventDefault(); first.focus();
      }
    };
    document.addEventListener('keydown', trapTab);

    return () => {
      window.clearTimeout(t);
      document.removeEventListener('keydown', trapTab);
      lastFocused?.focus?.();
    };
  }, [active, scopeRef, layerIdRef]);
}
