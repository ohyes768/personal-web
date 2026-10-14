/** Limited in-memory page cache; decisions clear it and external changes expire it. */
export class WorkspacePageCache<T> {
  private pages = new Map<string, { value: T; expires: number }>();
  constructor(private limit = 12, private ttl = 60_000, private clock = Date.now) {}
  get(key: string): T | undefined {
    const entry = this.pages.get(key);
    if (!entry) return undefined;
    if (entry.expires <= this.clock()) { this.pages.delete(key); return undefined; }
    return entry.value;
  }
  set(key: string, value: T) {
    this.pages.delete(key);
    this.pages.set(key, { value, expires: this.clock() + this.ttl });
    while (this.pages.size > this.limit) this.pages.delete(this.pages.keys().next().value!);
  }
  clear() { this.pages.clear(); }
}
