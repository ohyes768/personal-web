/** 展示用任务名：剥掉登记名尾部的括号注记，如「选股（Hermes/ohyes768）」→「选股」 */
export function taskDisplayName(name: string): string {
  return name.replace(/（[^）]*）\s*$/, "").trim() || name;
}
