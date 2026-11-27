"use client";

// 诊断用错误边界：把真实异常显示出来而不是笼统的 Application error
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="p-6 bg-red-50 border border-red-200 rounded-lg">
      <h2 className="font-semibold text-red-700 mb-2">页面出错了</h2>
      <pre className="text-xs whitespace-pre-wrap text-red-600 mb-3">
        {error.message}
        {"\n"}
        {error.stack}
      </pre>
      <button onClick={reset} className="px-3 py-1.5 text-sm rounded-md bg-red-600 text-white cursor-pointer">
        重试
      </button>
    </div>
  );
}
