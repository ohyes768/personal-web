/**
 * 加载遮罩组件
 */
interface LoadingOverlayProps {
  message?: string;
}

export function LoadingOverlay({ message = '加载中...' }: LoadingOverlayProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-4">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <p className="text-lg text-gray-200">{message}</p>
      </div>
    </div>
  );
}
