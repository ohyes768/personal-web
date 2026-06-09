/**
 * 暗色模式 Hook
 * 检测系统颜色偏好
 */
import { useState, useEffect } from 'react';

export function useDarkMode(): boolean {
  const [isDarkMode, setIsDarkMode] = useState(false);

  useEffect(() => {
    // 客户端环境下检测系统颜色偏好
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    // 初始化状态
    setIsDarkMode(mediaQuery.matches);

    // 监听系统颜色变化
    const handleChange = (e: MediaQueryListEvent) => {
      setIsDarkMode(e.matches);
    };

    // 现代浏览器使用 addEventListener
    mediaQuery.addEventListener('change', handleChange);

    // 清理
    return () => {
      mediaQuery.removeEventListener('change', handleChange);
    };
  }, []);

  return isDarkMode;
}
