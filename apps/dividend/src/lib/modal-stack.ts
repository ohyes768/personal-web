/**
 * modal-stack — 弹层层级栈（Modal / 抽屉共用）。
 *
 * 解决的问题：抽屉打开时键盘仍可叠开弹框，此前两个组件各自挂 document Esc 监听，
 * 一次按键两层同关，未保存的编辑态随之蒸发。现在按打开顺序记录层级，
 * Esc 只让最顶层响应（关闭后焦点归还到下一层，Esc 一次退一层）。
 * 焦点圈同理只对最顶层生效，避免内层 trap 与顶层抢焦点。
 */
const stack: symbol[] = [];

/** 弹层打开时调用，返回本层 id；返回的 id 需在关闭时传给 popLayer。 */
export function pushLayer(): symbol {
  const id = Symbol('overlay-layer');
  stack.push(id);
  return id;
}

export function popLayer(id: symbol): void {
  const i = stack.indexOf(id);
  if (i >= 0) stack.splice(i, 1);
}

/** 是否存在比 id 更晚打开（即叠在 id 之上）的弹层 */
export function hasLayerOnTop(id: symbol): boolean {
  const i = stack.indexOf(id);
  return i >= 0 && i < stack.length - 1;
}
