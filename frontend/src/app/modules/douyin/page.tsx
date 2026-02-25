"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080';

interface VideoItem {
  aweme_id: string;
  success: boolean;
  error_message?: string;
  info?: {
    title: string;
    author: string;
    create_time: string;
    share_url: string;
  };
  transcript?: {
    formatted_text?: string;
    text?: string;
    audio_duration: number;
    confidence: number;
  };
}

interface VideoListResponse {
  total: number;
  page: number;
  page_size: number;
  videos: VideoItem[];
}

export default function DouyinPage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collectMessage, setCollectMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const pageSize = 20;

  const fetchVideos = async (keyword?: string, isRefresh: boolean = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const apiUrl = keyword
        ? `${API_BASE_URL}/api/douyin/search?keyword=${encodeURIComponent(keyword)}&page=${page}&page_size=${pageSize}`
        : `${API_BASE_URL}/api/douyin/videos?page=${page}&page_size=${pageSize}`;

      const response = await fetch(apiUrl);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: VideoListResponse = await response.json();
      setVideos(data.videos || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取数据失败");
      console.error("Error fetching videos:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = async () => {
    // 触发采集
    setCollecting(true);
    setCollectMessage("正在启动采集任务...");

    try {
      const response = await fetch(`${API_BASE_URL}/api/douyin/collect`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      if (!data.success) {
        setCollectMessage(data.message || "采集任务启动失败");
        setTimeout(() => {
          setCollecting(false);
          setCollectMessage("");
        }, 3000);
        return;
      }

      setCollectMessage("采集任务已启动，正在处理...");

      // 轮询采集状态
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await fetch(
            `${API_BASE_URL}/api/douyin/collect/status`
          );
          const statusData = await statusResponse.json();

          if (!statusData.running) {
            // 采集完成
            clearInterval(pollInterval);
            setCollectMessage(statusData.message || "采集完成");

            setTimeout(() => {
              setCollecting(false);
              setCollectMessage("");
              // 重新加载数据
              setPage(1);
              fetchVideos(searchKeyword || undefined, true);
            }, 2000);
          }
        } catch (err) {
          clearInterval(pollInterval);
          setCollectMessage("获取采集状态失败");
          setTimeout(() => {
            setCollecting(false);
            setCollectMessage("");
          }, 3000);
        }
      }, 2000); // 每 2 秒查询一次状态

      // 5 分钟后停止轮询（防止无限轮询）
      setTimeout(() => {
        clearInterval(pollInterval);
        if (collecting) {
          setCollecting(false);
          setCollectMessage("采集超时，请手动刷新");
        }
      }, 300000);
    } catch (err) {
      setCollectMessage(err instanceof Error ? err.message : "启动采集失败");
      setTimeout(() => {
        setCollecting(false);
        setCollectMessage("");
      }, 3000);
    }
  };

  useEffect(() => {
    fetchVideos(searchKeyword || undefined);
  }, [page]);

  const handleSearch = () => {
    setPage(1);
    fetchVideos(searchKeyword || undefined);
  };

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="max-w-7xl mx-auto p-8">
        {/* 头部导航 */}
        <div className="mb-8">
          <div className="flex justify-between items-start">
            <div>
              <Link
                href="/"
                className="text-gray-400 hover:text-white transition-colors"
              >
                ← 返回首页
              </Link>
              <h1 className="text-4xl font-bold mt-4">抖音视频文字稿</h1>
              <p className="text-gray-400 mt-2">
                财经博主视频转文字稿，共 {total} 个视频
              </p>
            </div>
            <div className="text-right flex items-center gap-2">
              <button
                onClick={handleRefresh}
                disabled={refreshing || loading || collecting}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg transition-colors flex items-center gap-2"
                title="获取所有收藏视频，最多采集10个并进行语音识别，可能需要较长时间"
              >
                <svg
                  className={`w-5 h-5 ${collecting ? "animate-spin" : ""}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                {collecting ? "采集中..." : "采集新数据"}
              </button>
              <div className="group relative">
                <svg
                  className="w-5 h-5 text-gray-400 cursor-help"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-gray-800 border border-gray-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-10">
                  <p className="text-gray-300 text-sm">
                    获取所有收藏视频，最多采集10个并进行语音识别，可能需要较长时间
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* 采集状态提示 */}
          {collectMessage && (
            <div className="mt-4 p-4 bg-blue-900/50 border border-blue-700 rounded-lg">
              <p className="text-blue-200">{collectMessage}</p>
            </div>
          )}
        </div>

        {/* 搜索栏 */}
        <div className="mb-8 flex gap-4">
          <input
            type="text"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && handleSearch()}
            placeholder="搜索标题、作者或内容关键词..."
            className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleSearch}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
          >
            搜索
          </button>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mb-8 p-4 bg-red-900/50 border border-red-700 rounded-lg">
            <p className="text-red-200">错误: {error}</p>
            <p className="text-red-300 text-sm mt-2">
              请确保后端服务已启动: python -m uvicorn api_server:app --port 8093
            </p>
          </div>
        )}

        {/* 加载状态 */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
            <p className="mt-4 text-gray-400">加载中...</p>
          </div>
        )}

        {/* 视频列表 */}
        {!loading && videos && videos.length > 0 && (
          <>
            <div className="grid grid-cols-1 gap-6 mb-8">
              {videos.map((video) => (
                <Link
                  key={video.aweme_id}
                  href={`/modules/douyin/${video.aweme_id}`}
                  className="block p-6 bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors border border-gray-800"
                >
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-xl font-bold flex-1 pr-4">
                      {video.info?.title || "未知标题"}
                    </h3>
                    {video.transcript && (
                      <span className="px-3 py-1 bg-green-900/50 text-green-300 text-sm rounded-full whitespace-nowrap">
                        已识别
                      </span>
                    )}
                  </div>

                  <p className="text-gray-400 mb-2">
                    作者: {video.info?.author || "未知"}
                  </p>

                  <p className="text-gray-600 text-sm">
                    {video.info?.create_time || "未知时间"}
                  </p>
                </Link>
              ))}
            </div>

            {/* 分页 */}
            {total > pageSize && (
              <div className="flex justify-center gap-4">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  上一页
                </button>
                <span className="px-4 py-2 text-gray-400">
                  第 {page} 页，共 {Math.ceil(total / pageSize)} 页
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= Math.ceil(total / pageSize)}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}

        {/* 空状态 */}
        {!loading && videos.length === 0 && !error && (
          <div className="text-center py-12">
            <p className="text-gray-400 text-lg">暂无视频数据</p>
            {searchKeyword && (
              <p className="text-gray-500 text-sm mt-2">
                尝试使用其他关键词搜索
              </p>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
