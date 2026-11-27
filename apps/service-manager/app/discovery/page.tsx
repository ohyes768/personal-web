"use client";

import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  api,
  ApiError,
  type DiscoveryCandidate,
  type DiscoveryResponse,
} from "@/lib/api";
import { composeFileText, containerTone, formatRelative, HEALTH, portText } from "@/lib/status";
import { StateBadge, Spinner, Toast } from "@/components/Widgets";
import { describeJob, waitForJob } from "@/lib/jobs";
import { DockerNotice } from "@/components/DockerNotice";

export default function DiscoveryPage() {
  return (
    <Suspense>
      <DiscoveryView />
    </Suspense>
  );
}

function DiscoveryView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [data, setData] = useState<DiscoveryResponse | null>(null);
  const [project, setProject] = useState("");
  const [state, setState] = useState("");
  const [ignored, setIgnored] = useState<"all" | "active" | "ignored">(
    searchParams.get("ignored") === "ignored"
      ? "ignored"
      : searchParams.get("ignored") === "all"
        ? "all"
        : "active",
  );
  const [bound, setBound] = useState<"all" | "unbound" | "bound">(
    searchParams.get("bound") === "bound" ? "bound" : searchParams.get("bound") === "all" ? "all" : "unbound",
  );
  const [includeEphemeral, setIncludeEphemeral] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [attachTo, setAttachTo] = useState("");
  const [services, setServices] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [toastKind, setToastKind] = useState<"ok" | "error">("ok");
  function notify(message: string, kind: "ok" | "error" = "ok") {
    setToastKind(kind);
    setToast(message);
  }
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.discovery({
        project,
        state,
        ignored: ignored === "all" ? null : ignored === "ignored",
        include_ephemeral: includeEphemeral,
        bound: bound === "all" ? null : bound === "bound",
      });
      setData(result);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载候选失败");
    } finally {
      setLoading(false);
    }
  }, [project, state, ignored, includeEphemeral, bound]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api
      .listServices({ page_size: 100 })
      .then((result) =>
        setServices(result.items.map((item) => ({ id: item.id, name: item.name }))),
      )
      .catch(() => setServices([]));
  }, []);

  const items = useMemo(() => data?.items ?? [], [data]);
  const selectedItems = useMemo(
    () => items.filter((item) => selected.includes(item.source_key)),
    [items, selected],
  );
  // 已归属的容器要能看出归到谁名下：按 service_id 查名字
  const serviceNames = useMemo(
    () => new Map(services.map((item) => [item.id, item.name])),
    [services],
  );

  function toggle(sourceKey: string) {
    setSelected((current) =>
      current.includes(sourceKey)
        ? current.filter((item) => item !== sourceKey)
        : [...current, sourceKey],
    );
  }

  async function scan() {
    if (scanning) return;
    const label = "容器扫描";
    setScanning(true);
    try {
      const job = await api.refresh("docker");
      notify(
        job.deduplicated ? "已有同类型任务在跑，复用现有任务" : `已提交${label}任务`,
      );
      // 与「服务」页一致：轮询到终态再刷新，固定 3 秒会漏掉慢任务的结果。
      const result = await waitForJob(job.id);
      if (result.timedOut) {
        notify(`${label}还没跑完，仍在后台执行，稍后再看`);
      } else if (result.job) {
        const failed =
          result.job.state === "failed" ||
          result.job.state === "partial_failed" ||
          result.job.state === "interrupted";
        notify(describeJob(label, result.job), failed ? "error" : "ok");
      }
      await load();
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : `${label}失败`, "error");
    } finally {
      setScanning(false);
    }
  }

  async function doImport() {
    if (selected.length === 0) {
      notify("先勾选要导入的组件", "error");
      return;
    }
    if (!attachTo && !name.trim()) {
      notify("新建服务需要填写名称", "error");
      return;
    }
    try {
      const result = await api.importComponents({
        components: selected.map((sourceKey) => ({ source_key: sourceKey, required: true })),
        service_id: attachTo || null,
        name: attachTo ? null : name.trim(),
        description,
        tags: [],
      });
      setSelected([]);
      setName("");
      setDescription("");
      setAttachTo("");
      notify(result.created ? "已新建服务并关联组件" : "已追加到现有服务");
      router.push("/");
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : "导入失败", "error");
    }
  }

  async function toggleIgnore(sourceKeys: string[], next: boolean) {
    try {
      await api.setIgnored(sourceKeys, next);
      notify(next ? "已忽略" : "已取消忽略");
      await load();
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : "操作失败", "error");
    }
  }

  return (
    <>
      <h1>容器管理</h1>
      <p className="lead">全部容器，与台账的对应关系。</p>

      {data && !data.docker_available ? <DockerNotice error={data.docker_error} /> : null}

      <div className="card tight">
        <div className="filter-grid">
          <label className="field" htmlFor="filter-project">
            Compose 项目
            <select
              id="filter-project"
              value={project}
              onChange={(event) => setProject(event.target.value)}
            >
              <option value="">全部</option>
              {(data?.projects ?? []).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="field" htmlFor="filter-state">
            状态
            <select
              id="filter-state"
              value={state}
              onChange={(event) => setState(event.target.value)}
            >
              <option value="">全部</option>
              <option value="running">运行中</option>
              <option value="exited">已退出</option>
              <option value="missing">已消失</option>
            </select>
          </label>
          <label className="field" htmlFor="filter-bound">
            入账状态
            <select
              id="filter-bound"
              value={bound}
              onChange={(event) => setBound(event.target.value as typeof bound)}
            >
              <option value="unbound">未入账</option>
              <option value="bound">已入账</option>
              <option value="all">全部</option>
            </select>
          </label>
          <label className="field" htmlFor="filter-ignored">
            忽略状态
            <select
              id="filter-ignored"
              value={ignored}
              onChange={(event) => setIgnored(event.target.value as typeof ignored)}
            >
              <option value="active">未忽略</option>
              <option value="ignored">已忽略</option>
              <option value="all">全部</option>
            </select>
          </label>
          <label
            className="small"
            style={{ display: "inline-flex", gap: 6, alignItems: "center", justifyContent: "flex-end" }}
          >
            <input
              type="checkbox"
              checked={includeEphemeral}
              onChange={(event) => setIncludeEphemeral(event.target.checked)}
            />
            显示一次性 / 已退出容器
          </label>
        </div>
        <div className="btn-row">
          <button
            className="btn"
            type="button"
            disabled={scanning}
            aria-busy={scanning}
            onClick={() => void scan()}
          >
            {scanning ? (
              <>
                <Spinner />
                扫描中…
              </>
            ) : (
              "扫描容器"
            )}
          </button>
          {data?.last_success_at ? (
            <span className="scan-caption">上次扫描 {formatRelative(data.last_success_at)}</span>
          ) : null}
        </div>
      </div>

      {data?.counts ? (
        <p className="small muted">
          {data.counts.total} 个容器 · {data.counts.bound} 已入账 · {data.counts.unbound} 未入账
          {data.counts.ignored > 0 ? `（已忽略 ${data.counts.ignored}）` : ""} · 当前显示 {items.length} 条
        </p>
      ) : null}

      {error ? <p className="notice bad">{error}</p> : null}

      {selected.length ? (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>导入 {selected.length} 个组件</h2>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="import-attach">追加到现有服务</label>
              <select
                id="import-attach"
                value={attachTo}
                onChange={(event) => setAttachTo(event.target.value)}
              >
                <option value="">（新建服务）</option>
                {services.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            {attachTo ? null : (
              <>
                <div className="field">
                  <label htmlFor="import-name">新服务名称</label>
                  <input
                    id="import-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                </div>
              </>
            )}
          </div>
          {attachTo ? null : (
            <div className="field">
              <label htmlFor="import-desc">用途</label>
              <textarea
                id="import-desc"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
          )}
          <div className="btn-row">
            <button className="btn primary" type="button" onClick={() => void doImport()}>
              确认导入
            </button>
            <button className="btn" type="button" onClick={() => setSelected([])}>
              取消选择
            </button>
          </div>
          <p className="small muted">
            已选：{selectedItems.map((item) => item.container_name).join("、")}
          </p>
        </div>
      ) : null}

      {loading ? (
        <p className="muted">加载中…</p>
      ) : items.length === 0 ? (
        <div className="card">
          <p className="muted">
            {data?.docker_available
              ? "没有匹配的候选容器。可以换个筛选条件，或点「扫描容器」刷新。"
              : "Docker 不可用时没有候选；已有台账仍可在「服务」页维护。"}
          </p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="cols-fit">
            <thead>
              <tr>
                <th style={{ width: "5%" }}>选择</th>
                <th className="col-name">容器</th>
                <th className="col-state">状态</th>
                <th className="col-port">端口</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item: DiscoveryCandidate) => (
                <tr key={item.source_key}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.includes(item.source_key)}
                      disabled={!item.bindable}
                      onChange={() => toggle(item.source_key)}
                      aria-label={`选择 ${item.container_name}`}
                    />
                  </td>
                  <td>
                    <div className="mono">{item.container_name}</div>
                    <div className="small muted truncate">{item.image_ref}</div>
                    <div className="small muted truncate">
                      {item.project ?? "无 Compose 项目"}
                      {item.service_name ? ` · ${item.service_name}` : ""}
                    </div>
                    <div className="small muted truncate">
                      {item.compose_working_dir ?? "部署路径未知"}
                      {item.compose_files.map((file) => `（${composeFileText(file)}）`)}
                    </div>
                    {item.oneoff ? <span className="badge warn">一次性任务</span> : null}
                    {item.bound_service_id ? (
                      <span className="badge info">
                        已归属 → {serviceNames.get(item.bound_service_id) ?? item.bound_service_id}
                      </span>
                    ) : null}
                  </td>
                  <td>
                    <StateBadge tone={containerTone(item.state)} />
                    {item.health !== "not_configured" ? (
                      <div className="small">
                        <StateBadge tone={HEALTH[item.health]} />
                      </div>
                    ) : null}
                  </td>
                  <td className="small mono">
                    {item.ports.length === 0 ? (
                      <span className="muted">
                        {item.network_mode === "host" ? "宿主网络" : "—"}
                      </span>
                    ) : (
                      item.ports.slice(0, 4).map((port, index) => (
                        <div key={index}>{portText(port)}</div>
                      ))
                    )}
                  </td>
                  <td>
                    <div className="row-actions">
                      {item.ignored ? (
                        <button
                          className="btn btn-mini"
                          type="button"
                          onClick={() => void toggleIgnore([item.source_key], false)}
                        >
                          取消忽略
                        </button>
                      ) : (
                        <button
                          className="btn btn-mini"
                          type="button"
                          onClick={() => void toggleIgnore([item.source_key], true)}
                        >
                          忽略
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Toast message={toast} kind={toastKind} onDismiss={() => setToast(null)} />
    </>
  );
}
