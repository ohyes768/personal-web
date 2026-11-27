"use client";

// 三态兜底：加载骨架 / 错误重试 / 空态。所有视图共用，fetch 失败不白屏。
export function Loading({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="py-16 text-center text-sm text-gray-400 animate-pulse">{label}</div>
  );
}

export function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="my-10 text-center">
      <p className="text-sm text-red-600">{error}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer"
        >
          重试
        </button>
      )}
    </div>
  );
}

export function Empty({ hint }: { hint: string }) {
  return <div className="py-16 text-center text-sm text-gray-400">{hint}</div>;
}
