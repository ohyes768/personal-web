"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type ServiceListItem, type SummaryResponse } from "@/lib/api";
import {
  abnormalTones,
  describeCheck,
  formatRelative,
  HEALTH,
  RELEASE_STATE,
  RUNTIME,
  TLS_STATE,
  URL_STATE,
} from "@/lib/status";
import SessionGate from "@/components/SessionGate";
import { SafeLink, StateBadge, Toast } from "@/components/Widgets";

export default function HomePage() {
  return (
    <SessionGate>
      <ServiceList />
    </SessionGate>
  );
}

function ServiceList() {
  const [items, setItems] = useState<ServiceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [onlyAbnormal, setOnlyAbnormal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, totals] = await Promise.all([
        api.listServices({ query, category, page: 1, page_size: 100 }),
        api.summary(),
      ]);
      setItems(list.items);
      setTotal(list.total);
      setSummary(totals);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [query, category]);

  useEffect(() => {
    void load();
  }, [load]);

  const categories = useMemo(
    () => Array.from(new Set(items.map((item) => item.category).filter(Boolean))).sort(),
    [items],
  );

  const visible = useMemo(
    () =>
      onlyAbnormal
        ? items.filter((item) => abnormalTones(item.status).length > 0)
        : items,
    [items, onlyAbnormal],
  );

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!newName.trim()) return;
    try {
      await api.createService({ name: newName.trim(), category: newCategory.trim() });
      setNewName("");
      setNewCategory("");
      setCreating(false);
      setToast("已新增服务");
      await load();
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "新增失败");
    }
  }

  async function refresh(kind: "docker" | "all") {
    try {
      const job = await api.refresh(kind);
      setToast(job.deduplicated ? "已有同类型任务在跑，复用现有任务" : `已提交${kind === "docker" ? "容器扫描" : "全量检查"}任务`);
      window.setTimeout(() => void load(), 3000);
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "刷新失败");
    }
  }

  return (
    <>
      <h1>服务</h1>
      <p className="lead">
        台账里的服务、它们对应的容器、入口与证书。状态分维度显示，不用一个绿灯抹平。
      </p>

      {summary ? (
        <div className="kpi-row">
          <div className="kpi">
            <div className="num">{summary.services}</div>
            <div className="lbl">业务服务</div>
          </div>
          <div className="kpi">
            <div className="num">{summary.components}</div>
            <div className="lbl">已关联组件</div>
          </div>
          <div className="kpi">
            <div className="num" style={{ color: summary.docker_available ? "var(--ok)" : "var(--warn)" }}>
              {summary.docker_available ? "可用" : "不可用"}
            </div>
            <div className="lbl">Docker 读取</div>
          </div>
          <div className="kpi">
            <div className="num">{summary.unread_releases}</div>
            <div className="lbl">未读发布</div>
          </div>
          <div className="kpi">
            <div className="num small" style={{ fontSize: 13 }}>
              {formatRelative(summary.docker_last_success_at)}
            </div>
            <div className="lbl">上次扫描</div>
          </div>
        </div>
      ) : null}

      {summary && !summary.docker_available ? (
        <div className="notice">
          <span>Docker 读取不可用：{summary.docker_error ?? "未配置"}。人工台账仍可正常使用。</span>
        </div>
      ) : null}

      <div className="card tight">
        <div className="btn-row">
          <input
            type="search"
            placeholder="搜索名称 / 用途 / 标签 / 域名 / 端口 / 路径"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="搜索服务"
            style={{ flex: "1 1 320px" }}
          />
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            aria-label="按分类筛选"
          >
            <option value="">全部分类</option>
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <label className="small" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={onlyAbnormal}
              onChange={(event) => setOnlyAbnormal(event.target.checked)}
            />
            只看异常
          </label>
          <button className="btn" type="button" onClick={() => void refresh("docker")}>
            扫描容器
          </button>
          <button className="btn" type="button" onClick={() => void refresh("all")}>
            全量检查
          </button>
          <button className="btn primary" type="button" onClick={() => setCreating((value) => !value)}>
            新增服务
          </button>
        </div>

        {creating ? (
          <form onSubmit={create} style={{ marginTop: 12 }}>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="new-name">名称（必填）</label>
                <input
                  id="new-name"
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="new-category">分类</label>
                <input
                  id="new-category"
                  value={newCategory}
                  onChange={(event) => setNewCategory(event.target.value)}
                  placeholder="金融 / 媒体 / 基础设施"
                />
              </div>
            </div>
            <button className="btn primary" type="submit">
              保存
            </button>
          </form>
        ) : null}
      </div>

      {error ? <p className="notice bad">{error}</p> : null}

      {loading ? (
        <p className="muted">加载中…</p>
      ) : visible.length === 0 ? (
        <div className="card">
          <p>
            {items.length === 0
              ? "台账还是空的。可以先「新增服务」，或到「发现导入」从运行中的容器建立。"
              : "没有匹配的服务。"}
          </p>
          <div className="btn-row">
            <Link className="btn" href="/discovery">
              去发现导入
            </Link>
          </div>
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>服务</th>
                <th>主入口</th>
                <th>运行</th>
                <th>健康</th>
                <th>URL</th>
                <th>TLS</th>
                <th>发布</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link href={`/service/${item.id}`}>{item.name}</Link>
                    {item.category ? <div className="small muted">{item.category}</div> : null}
                    {item.tags.length ? (
                      <div className="small muted">{item.tags.join(" · ")}</div>
                    ) : null}
                  </td>
                  <td>
                    {item.primary_url ? (
                      <SafeLink href={item.primary_url} className="mono wrap-anywhere">
                        {item.primary_url}
                      </SafeLink>
                    ) : (
                      <span className="muted small">未登记入口</span>
                    )}
                  </td>
                  <td>
                    <StateBadge tone={RUNTIME[item.status.runtime]} />
                    <div className="small muted">{item.component_count} 个组件</div>
                  </td>
                  <td>
                    <StateBadge tone={HEALTH[item.status.health]} />
                  </td>
                  <td>
                    <StateBadge tone={URL_STATE[item.status.url]} title={describeCheck(item.status.url_check)} />
                  </td>
                  <td>
                    <StateBadge tone={TLS_STATE[item.status.tls]} title={describeCheck(item.status.tls_check)} />
                  </td>
                  <td>
                    <StateBadge tone={RELEASE_STATE[item.status.release]} />
                    {item.status.unread_releases > 0 ? (
                      <div className="small muted">{item.status.unread_releases} 条未读</div>
                    ) : null}
                  </td>
                  <td>
                    <div className="row-actions">
                      <Link className="btn btn-mini" href={`/service/${item.id}`}>
                        详情
                      </Link>
                      {item.primary_url ? (
                        <SafeLink className="btn btn-mini" href={item.primary_url}>
                          打开
                        </SafeLink>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted">共 {total} 个服务</p>
      <Toast message={toast} />
    </>
  );
}
