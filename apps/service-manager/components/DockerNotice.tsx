"use client";

/** Docker 数据源不可用时的提示条。服务页与容器管理页共用同一句文案。 */
export function DockerNotice({ error }: { error: string | null }) {
  return (
    <div className="notice">
      <span>
        Docker 读取不可用：{error ?? "未配置"}。人工台账仍可正常使用，运行状态显示上次成功扫描的缓存数据。
      </span>
    </div>
  );
}
