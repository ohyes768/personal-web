/**
 * 基本面资料阅读入口（主页面 → 独立阅读页）
 *
 * 用普通同源 <a> 做完整导航（不做 Next 客户端路由）：
 * 线上部署时应用 basePath 为空、nginx 剥掉 /dividend 前缀，
 * 客户端路由会按带前缀路径取缓存导致不一致，完整导航最稳。
 *
 * 服务端/水合前使用同目录相对 href ./quality-reader（本地与线上都能解析到正确地址），
 * 挂载后再按浏览器真实 pathname 计算绝对地址并带上返回视图参数。
 */
'use client';

import { useEffect, useState } from 'react';
import { readerHref } from '@/lib/quality-reader';

export interface QualityReaderEntryProps {
  /** 主页面当前 query（tab / fav 等），用于回跳时还原视图 */
  sourceQuery: string;
}

export function QualityReaderEntry({ sourceQuery }: QualityReaderEntryProps) {
  const [href, setHref] = useState('./quality-reader');

  useEffect(() => {
    setHref(readerHref(window.location.pathname, new URLSearchParams(sourceQuery)));
  }, [sourceQuery]);

  return (
    <a
      href={href}
      className="quality-reader-entry"
      data-testid="quality-reader-entry"
    >
      基本面资料阅读
    </a>
  );
}
