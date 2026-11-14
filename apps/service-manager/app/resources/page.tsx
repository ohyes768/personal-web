"use client";

/** 资源总览：只保留**端口**视图。

 * 域名与证书视图已下线——它们的数据源是服务台账里的「入口」，而入口维护
 * 已随详情页一起下线（见 .trellis/spec/apps/service-manager/frontend/index.md）。
 * 后端对应接口仍在，只是不再有界面入口。
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type PortOverviewResponse } from "@/lib/api";
import { portKindLabel, portText } from "@/lib/status";
import SessionGate from "@/components/SessionGate";
import { Toast } from "@/components/Widgets";

export default function ResourcesPage() {
  return (
    <SessionGate>
      <ResourcesView />
    </SessionGate>
  );
}

function ResourcesView() {
  const [query, setQuery] = useState("");
  const [onlyRegistered, setOnlyRegistered] = useState(false);
  const [ports, setPorts] = useState<PortOverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPorts(await api.ports({ only_registered: onlyRegistered, query }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载失败");
    }
  }, [query, onlyRegistered]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <h1>资源总览</h1>
      <p className="lead">
        NAS 上各容器占用的端口与可能的重叠。镜像、部署路径、数据卷这些去 Docker 那边看。
      </p>

      <div className="card tight">
        <div className="btn-row">
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索主机 / 端口 / 服务"
            aria-label="搜索资源"
            style={{ flex: "1 1 260px" }}
          />
          <label className="small" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={onlyRegistered}
              onChange={(event) => setOnlyRegistered(event.target.checked)}
            />
            仅已登记服务
          </label>
        </div>
      </div>

      {error ? <p className="notice bad">{error}</p> : null}

      {ports ? (
        <>
          <div className="notice info">
            <span>{ports.scope_note}</span>
          </div>
          {ports.overlaps.length ? (
            <div className="notice">
              <div>
                <strong>潜在端口重叠（需人工核查）</strong>
                <ul className="small" style={{ margin: "6px 0 0 16px", padding: 0 }}>
                  {ports.overlaps.map((pair) => (
                    <li key={`${pair.left}-${pair.right}`} className="mono">
                      {pair.left} ↔ {pair.right}
                    </li>
                  ))}
                </ul>
                <p className="small" style={{ margin: "6px 0 0" }}>
                  仅同主机、同协议、同地址族且绑定 IP 重叠时提示；不代表 Docker 已成功运行冲突绑定。
                </p>
              </div>
            </div>
          ) : null}
          {ports.items.length === 0 ? (
            <p className="muted">没有端口记录。若 Docker 读取不可用，请到「设置」查看原因。</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>端口</th>
                    <th>类型</th>
                    <th>容器</th>
                    <th>服务</th>
                    <th>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {ports.items.map((row, index) => (
                    <tr key={`${row.source_key}-${row.host_port}-${row.container_port}-${index}`}>
                      <td className="mono">{portText(row)}</td>
                      <td className="small">{portKindLabel(row.kind)}</td>
                      <td className="small">
                        {row.container_name || "—"}
                        {row.project ? <div className="muted">{row.project}</div> : null}
                      </td>
                      <td className="small">
                        {row.service_name ? (
                          <span>{row.service_name}</span>
                        ) : (
                          <span className="muted">未登记</span>
                        )}
                      </td>
                      <td className="small">
                        {row.origin === "manual" ? "人工" : "Docker"}
                        {row.note ? <div className="muted">{row.note}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}

      <Toast message={toast} />
    </>
  );
}
