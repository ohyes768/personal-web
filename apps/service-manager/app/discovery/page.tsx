"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  ApiError,
  type DiscoveryCandidate,
  type DiscoveryResponse,
} from "@/lib/api";
import { composeFileText, formatRelative, HEALTH, portText } from "@/lib/status";
import SessionGate from "@/components/SessionGate";
import { StateBadge, Toast } from "@/components/Widgets";

export default function DiscoveryPage() {
  return (
    <SessionGate>
      <DiscoveryView />
    </SessionGate>
  );
}

function DiscoveryView() {
  const router = useRouter();
  const [data, setData] = useState<DiscoveryResponse | null>(null);
  const [project, setProject] = useState("");
  const [state, setState] = useState("");
  const [ignored, setIgnored] = useState<"all" | "active" | "ignored">("active");
  const [includeEphemeral, setIncludeEphemeral] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [attachTo, setAttachTo] = useState("");
  const [services, setServices] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.discovery({
        project,
        state,
        ignored: ignored === "all" ? null : ignored === "ignored",
        include_ephemeral: includeEphemeral,
      });
      setData(result);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载候选失败");
    } finally {
      setLoading(false);
    }
  }, [project, state, ignored, includeEphemeral]);

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
    try {
      await api.refresh("docker");
      setToast("已提交容器扫描，稍后刷新候选");
      window.setTimeout(() => void load(), 3000);
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "扫描失败");
    }
  }

  async function doImport() {
    if (selected.length === 0) {
      setToast("先勾选要导入的组件");
      return;
    }
    if (!attachTo && !name.trim()) {
      setToast("新建服务需要填写名称");
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
      setToast(result.created ? "已新建服务并关联组件" : "已追加到现有服务");
      router.push(`/service/${result.service_id}`);
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "导入失败");
    }
  }

  async function toggleIgnore(sourceKeys: string[], next: boolean) {
    try {
      await api.setIgnored(sourceKeys, next);
      setToast(next ? "已忽略" : "已取消忽略");
      await load();
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "操作失败");
    }
  }

  return (
    <>
      <h1>发现导入</h1>
      <p className="lead">
        从运行中的 Docker 容器建立服务。勾选多个组件可以合并成一个业务服务。
      </p>

      {data && !data.docker_available ? (
        <div className="notice">
          Docker 读取不可用：{data.docker_error ?? "未配置"}。已登记台账不受影响。
        </div>
      ) : null}
      {data?.last_success_at ? (
        <p className="small muted">上次成功扫描：{formatRelative(data.last_success_at)}</p>
      ) : null}

      <div className="card tight">
        <div className="btn-row">
          <select value={project} onChange={(event) => setProject(event.target.value)} aria-label="按项目筛选">
            <option value="">全部 Compose 项目</option>
            {(data?.projects ?? []).map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select value={state} onChange={(event) => setState(event.target.value)} aria-label="按状态筛选">
            <option value="">全部状态</option>
            <option value="running">运行中</option>
            <option value="exited">已退出</option>
            <option value="missing">已消失</option>
          </select>
          <select
            value={ignored}
            onChange={(event) => setIgnored(event.target.value as typeof ignored)}
            aria-label="按忽略状态筛选"
          >
            <option value="active">未忽略</option>
            <option value="ignored">已忽略</option>
            <option value="all">全部</option>
          </select>
          <label className="small" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={includeEphemeral}
              onChange={(event) => setIncludeEphemeral(event.target.checked)}
            />
            显示一次性 / 已退出容器
          </label>
          <button className="btn" type="button" onClick={() => void scan()}>
            扫描容器
          </button>
        </div>
      </div>

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
                <th className="col-meta">项目</th>
                <th className="col-state">状态</th>
                <th className="col-port">端口</th>
                <th className="col-path">部署路径</th>
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
                    <div className="small muted">{item.image_ref}</div>
                    {item.oneoff ? <span className="badge warn">一次性任务</span> : null}
                    {item.bound_service_id ? (
                      <span className="badge info">
                        已归属 → {serviceNames.get(item.bound_service_id) ?? item.bound_service_id}
                      </span>
                    ) : null}
                  </td>
                  <td className="small">
                    <div className="truncate" title={item.project ?? ""}>
                      {item.project ?? "（无 Compose 标签）"}
                    </div>
                    {item.service_name ? <div className="muted truncate">{item.service_name}</div> : null}
                  </td>
                  <td>
                    <span className="badge muted">{item.state}</span>
                    {item.health !== "not_configured" ? (
                      <div className="small">
                        <StateBadge tone={HEALTH[item.health]} />
                      </div>
                    ) : null}
                  </td>
                  <td className="small mono">
                    {item.ports.length === 0 ? (
                      <span className="muted">
                        {item.network_mode === "host" ? "宿主网络" : "无"}
                      </span>
                    ) : (
                      item.ports.slice(0, 4).map((port, index) => (
                        <div key={index}>{portText(port)}</div>
                      ))
                    )}
                  </td>
                  <td className="small mono">
                    <div className="truncate" title={item.compose_working_dir ?? ""}>
                      {item.compose_working_dir ?? "未知"}
                    </div>
                    {item.compose_files.map((file) => (
                      <div key={file.raw} className="muted truncate" title={composeFileText(file)}>
                        {composeFileText(file)}
                      </div>
                    ))}
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
                      {item.bound_service_id ? (
                        <Link className="btn btn-mini" href={`/service/${item.bound_service_id}`}>
                          查看服务
                        </Link>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Toast message={toast} />
    </>
  );
}
