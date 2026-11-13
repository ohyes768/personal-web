"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  type Ownership,
  type ServiceListItem,
  type SummaryResponse,
} from "@/lib/api";
import { describeJob, waitForJob } from "@/lib/jobs";
import {
  describeCheck,
  formatRelative,
  healthTooltip,
  HEALTH,
  invalidReasonOf,
  RELEASE_STATE,
  RUNTIME,
  tlsTooltip,
  tlsTone,
  URL_STATE,
} from "@/lib/status";
import SessionGate from "@/components/SessionGate";
import { SafeLink, Spinner, StateBadge, Toast } from "@/components/Widgets";

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
  const [group, setGroup] = useState<Ownership>("mine");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  // 刷新任务在后台跑，按钮各自转圈；两类任务互不阻塞。
  const [pending, setPending] = useState<{ docker: boolean; all: boolean }>({
    docker: false,
    all: false,
  });
  const aborters = useRef<Set<AbortController>>(new Set());
  // 同一类任务的防重入（state 更新要等一次渲染，用 ref 才能挡住连点）
  const inFlight = useRef<Set<"docker" | "all">>(new Set());

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

  // 离开页面时停掉还在轮询的刷新任务，别让后台继续空转
  useEffect(() => {
    const controllers = aborters.current;
    return () => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, []);

  const categories = useMemo(
    () => Array.from(new Set(items.map((item) => item.category).filter(Boolean))).sort(),
    [items],
  );

  // 分组：归属是台账里的一个字段（我维护的 / 别人的），逐条可改。
  const groups = useMemo(
    () => ({
      mine: items.filter((item) => item.ownership === "mine").length,
      other: items.filter((item) => item.ownership === "other").length,
    }),
    [items],
  );
  const tabItems = useMemo(
    () => items.filter((item) => item.ownership === group),
    [items, group],
  );

  async function changeOwnership(item: ServiceListItem, next: Ownership) {
    if (item.ownership === next) return;
    try {
      await api.patchService(item.id, { ownership: next, revision: item.revision });
      setToast(next === "mine" ? "已标为我维护的" : "已标为别人的");
      await load();
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "改归属失败");
    }
  }

  async function refresh(kind: "docker" | "all") {
    if (inFlight.current.has(kind)) return;
    const label = kind === "docker" ? "容器扫描" : "巡检";
    inFlight.current.add(kind);
    setPending((prev) => ({ ...prev, [kind]: true }));
    const controller = new AbortController();
    aborters.current.add(controller);
    try {
      const job = await api.refresh(kind);
      if (controller.signal.aborted) return;
      setToast(
        job.deduplicated
          ? "已有同类型任务在跑，复用现有任务"
          : `已提交${label}任务`,
      );
      // 任务在后台跑，轮询到终态再刷新列表——固定等 3 秒会漏掉慢任务的结果。
      const result = await waitForJob(job.id, { signal: controller.signal });
      if (result.aborted) return;
      if (result.timedOut) {
        setToast(`${label}还没跑完，仍在后台执行，稍后再看`);
      } else if (result.job) {
        setToast(describeJob(label, result.job));
      }
      await load();
    } catch (caught) {
      if (!controller.signal.aborted) {
        setToast(caught instanceof ApiError ? caught.message : `${label}失败`);
      }
    } finally {
      aborters.current.delete(controller);
      inFlight.current.delete(kind);
      setPending((prev) => ({ ...prev, [kind]: false }));
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
          <div
            className="kpi"
            title={`上次扫描观测到的容器总数：运行 ${summary.docker_running} · 已消失 ${summary.docker_missing}`}
          >
            <div className="num">{summary.docker_components}</div>
            <div className="lbl">发现容器</div>
          </div>
          <div
            className="kpi"
            title={`已关联到业务服务的容器：${summary.components} / ${summary.docker_components}`}
          >
            <div className="num">{summary.components}</div>
            <div className="lbl">已关联组件</div>
          </div>
          <div
            className="kpi"
            title={`发现但没关联到任何业务服务的容器：${summary.unregistered_components} 个，其中 ${summary.ignored_components} 个已标记忽略，实际待处理 ${summary.unregistered_components - summary.ignored_components} 个`}
          >
            <div
              className="num"
              style={{
                color:
                  summary.unregistered_components - summary.ignored_components > 0
                    ? "var(--warn)"
                    : undefined,
              }}
            >
              {summary.unregistered_components}
            </div>
            <div className="lbl">未入账</div>
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

      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={group === "mine"}
          className={group === "mine" ? "active" : ""}
          onClick={() => setGroup("mine")}
        >
          我维护的（{groups.mine}）
        </button>
        <button
          role="tab"
          aria-selected={group === "other"}
          className={group === "other" ? "active" : ""}
          onClick={() => setGroup("other")}
        >
          别人的（{groups.other}）
        </button>
      </div>

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
          <button
            className="btn"
            type="button"
            disabled={pending.docker}
            aria-busy={pending.docker}
            title="重新扫描 Docker 容器，刷新「发现容器 / 已关联组件 / 未入账」与各服务的运行、健康状态"
            onClick={() => void refresh("docker")}
          >
            {pending.docker ? (
              <>
                <Spinner />
                扫描中…
              </>
            ) : (
              "扫描容器"
            )}
          </button>
          <button
            className="btn"
            type="button"
            disabled={pending.all}
            aria-busy={pending.all}
            title="巡检全部已登记入口：URL 可达性、TLS 证书，并同步已配置的 GitHub 发布"
            onClick={() => void refresh("all")}
          >
            {pending.all ? (
              <>
                <Spinner />
                巡检中…
              </>
            ) : (
              "巡检"
            )}
          </button>
        </div>

        <p className="small muted" style={{ marginTop: 8 }}>
          巡检：逐一检查全部已登记入口的可达性与证书有效期，并同步已配置的 GitHub 发布；
          容器观测不在其中，由「扫描容器」负责（后台每 60 秒自动扫一次）。
        </p>
      </div>

      {error ? <p className="notice bad">{error}</p> : null}

      {loading ? (
        <p className="muted">加载中…</p>
      ) : tabItems.length === 0 ? (
        <div className="card">
          <p>
            {items.length === 0
              ? "台账还是空的。到「发现导入」从运行中的容器建立台账条目。"
              : `这个分组里没有服务（${group === "mine" ? "我维护的" : "别人的"}）。`}
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
                <th title="HTTPS 证书：有没有人信它、什么时候到期">证书</th>
                <th>发布</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tabItems.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link href={`/service/${item.id}`}>{item.name}</Link>
                    {item.description ? (
                      <div className="small truncate" title={item.description}>
                        {item.description}
                      </div>
                    ) : null}
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
                      <span
                        className="muted small"
                        title="网关、反向代理或内部调用类服务本就不需要对外入口，此项不适用、无需补录；若该服务确实需要 Web 访问，可在详情页登记入口"
                      >
                        无对外入口
                      </span>
                    )}
                  </td>
                  <td>
                    <StateBadge tone={RUNTIME[item.status.runtime]} />
                    <div className="small muted">{item.component_count} 个组件</div>
                  </td>
                  <td>
                    <StateBadge
                      tone={HEALTH[item.status.health]}
                      title={healthTooltip(undefined, item.status.health)}
                    />
                  </td>
                  <td>
                    <StateBadge tone={URL_STATE[item.status.url]} title={describeCheck(item.status.url_check)} />
                  </td>
                  <td>
                    <StateBadge
                      tone={tlsTone(
                        item.status.tls,
                        invalidReasonOf(item.status.tls_check),
                      )}
                      title={tlsTooltip(item.status.tls_check)}
                    />
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
                      <select
                        value={item.ownership}
                        onChange={(event) =>
                          void changeOwnership(item, event.target.value as Ownership)
                        }
                        aria-label={`${item.name} 的归属`}
                        title="这条服务是不是你维护的（决定列表分组）"
                        style={{ minHeight: 26, padding: "2px 6px", fontSize: 12 }}
                      >
                        <option value="mine">我维护的</option>
                        <option value="other">别人的</option>
                      </select>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted">
        共 {total} 个服务，当前分组 {tabItems.length} 个
      </p>
      <Toast message={toast} />
    </>
  );
}
