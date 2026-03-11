/**
 * Loading 组件
 * 通用加载状态组件
 */

export interface LoadingProps {
  message?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function Loading({ message = '加载中...', size = 'md' }: LoadingProps) {
  const sizeClasses = {
    sm: 'h-4 w-4 border-2',
    md: 'h-8 w-8 border-b-2',
    lg: 'h-12 w-12 border-b-4',
  };

  return (
    <div className="text-center py-12">
      <div className={`inline-block animate-spin rounded-full ${sizeClasses[size]} border-white`}></div>
      <p className="mt-4 text-gray-400">{message}</p>
    </div>
  );
}