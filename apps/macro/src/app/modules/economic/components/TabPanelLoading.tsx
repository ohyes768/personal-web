/**
 * Tab 内容区加载占位 — 只盖图表区域，不挡住顶栏 Tab
 */
interface TabPanelLoadingProps {
  message: string;
}

export function TabPanelLoading({ message }: TabPanelLoadingProps) {
  return (
    <div className="h-[700px] flex flex-col items-center justify-center gap-4 bg-gray-900 rounded-lg border border-gray-800">
      <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      <p className="text-gray-300">{message}</p>
    </div>
  );
}
