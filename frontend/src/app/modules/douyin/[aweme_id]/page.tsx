"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080';

interface VideoDetail {
  aweme_id: string;
  status: string;
  title: string;
  author: string;
  description: string;
  audio_url: string;
  transcript?: {
    text: string;
    segments?: Array<{
      start_time: number;
      end_time: number;
      text: string;
      confidence: number;
    }>;
    confidence: number;
    audio_duration: number;
  };
  processed_at?: number;
  upload_time?: string;
  error?: string;
}

export default function VideoDetailPage() {
  const params = useParams();
  const aweme_id = params.aweme_id as string;

  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchVideoDetail = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `${API_BASE_URL}/api/douyin/videos/${aweme_id}`
        );

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data: VideoDetail = await response.json();
        setVideo(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "获取视频详情失败");
        console.error("Error fetching video detail:", err);
      } finally {
        setLoading(false);
      }
    };

    if (aweme_id) {
      fetchVideoDetail();
    }
  }, [aweme_id]);

  const formatTime = (timestamp: number | string) => {
    if (!timestamp) return "未知";
    if (typeof timestamp === 'number') {
      return new Date(timestamp * 1000).toLocaleString("zh-CN");
    }
    return new Date(timestamp).toLocaleString("zh-CN");
  };

  // 根据状态显示不同的标签
  const renderStatusBadge = () => {
    if (!video) return null;

    switch (video.status) {
      case "completed":
        return (
          <span className="px-3 py-1 bg-green-900/50 text-green-300 text-sm rounded-full whitespace-nowrap">
            已识别
          </span>
        );
      case "processing":
        return (
          <span className="px-3 py-1 bg-yellow-900/50 text-yellow-300 text-sm rounded-full whitespace-nowrap">
            识别中
          </span>
        );
      case "failed":
        return (
          <span className="px-3 py-1 bg-red-900/50 text-red-300 text-sm rounded-full whitespace-nowrap">
            识别失败
          </span>
        );
      case "pending":
        return (
          <span className="px-3 py-1 bg-gray-700/50 text-gray-300 text-sm rounded-full whitespace-nowrap">
            待处理
          </span>
        );
      default:
        return null;
    }
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-black text-white">
        <div className="max-w-4xl mx-auto p-8">
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
            <p className="mt-4 text-gray-400">加载中...</p>
          </div>
        </div>
      </main>
    );
  }

  if (error || !video) {
    return (
      <main className="min-h-screen bg-black text-white">
        <div className="max-w-4xl mx-auto p-8">
          <Link
            href="/modules/douyin"
            className="text-gray-400 hover:text-white transition-colors inline-block mb-8"
          >
            ← 返回列表
          </Link>
          <div className="p-6 bg-red-900/50 border border-red-700 rounded-lg">
            <p className="text-red-200">错误: {error || "视频不存在"}</p>
          </div>
        </div>
      </main>
    );
  }

  // 如果处理失败，显示错误信息
  if (video.status === "failed") {
    return (
      <main className="min-h-screen bg-black text-white">
        <div className="max-w-4xl mx-auto p-8">
          <Link
            href="/modules/douyin"
            className="text-gray-400 hover:text-white transition-colors inline-block mb-8"
          >
            ← 返回列表
          </Link>

          <div className="mb-6">
            <h1 className="text-4xl font-bold mb-6 leading-tight">
              {video.title || "未知标题"}
            </h1>
            {renderStatusBadge()}
          </div>

          <div className="p-6 bg-red-900/50 border border-red-700 rounded-lg">
            <p className="text-red-300">识别失败: {video.error || "未知错误"}</p>
          </div>

          <div className="mt-8">
            <Link
              href="/modules/douyin"
              className="px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
            >
              返回列表
            </Link>
          </div>
        </div>
      </main>
    );
  }

  // 如果待处理，显示提示
  if (video.status === "pending" || video.status === "processing") {
    return (
      <main className="min-h-screen bg-black text-white">
        <div className="max-w-4xl mx-auto p-8">
          <Link
            href="/modules/douyin"
            className="text-gray-400 hover:text-white transition-colors inline-block mb-8"
          >
            ← 返回列表
          </Link>

          <div className="mb-6">
            <h1 className="text-4xl font-bold mb-6 leading-tight">
              {video.title || "未知标题"}
            </h1>
            {renderStatusBadge()}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8 p-6 bg-gray-900 rounded-lg">
            <div>
              <p className="text-gray-400 text-sm mb-1">作者</p>
              <p className="text-lg">{video.author || "未知"}</p>
            </div>
            <div>
              <p className="text-gray-400 text-sm mb-1">上传时间</p>
              <p className="text-lg">{formatTime(video.upload_time)}</p>
            </div>
          </div>

          <div className="p-6 bg-blue-900/50 border border-blue-700 rounded-lg">
            <p className="text-blue-200">
              {video.status === "processing" ? "视频正在识别中，请稍后再来查看" : "视频尚未处理，请在列表页点击\"处理待处理\"按钮"}
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="max-w-4xl mx-auto p-8">
        {/* 导航 */}
        <Link
          href="/modules/douyin"
          className="text-gray-400 hover:text-white transition-colors inline-block mb-8"
        >
          ← 返回列表
        </Link>

        {/* 视频标题 */}
        <h1 className="text-4xl font-bold mb-6 leading-tight">
          {video.title || "未知标题"}
        </h1>

        {/* 视频信息 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8 p-6 bg-gray-900 rounded-lg">
          <div>
            <p className="text-gray-400 text-sm mb-1">作者</p>
            <p className="text-lg">{video.author || "未知"}</p>
          </div>
          <div>
            <p className="text-gray-400 text-sm mb-1">上传时间</p>
            <p className="text-lg">{formatTime(video.upload_time)}</p>
          </div>
          {video.transcript && (
            <>
              <div>
                <p className="text-gray-400 text-sm mb-1">音频时长</p>
                <p className="text-lg">
                  {video.transcript.audio_duration.toFixed(2)} 秒
                </p>
              </div>
              <div>
                <p className="text-gray-400 text-sm mb-1">识别置信度</p>
                <p className="text-lg">
                  {(video.transcript.confidence * 100).toFixed(1)}%
                </p>
              </div>
            </>
          )}
        </div>

        {/* 描述 */}
        {video.description && video.description !== video.title && (
          <div className="bg-gray-900 rounded-lg p-6 mb-8">
            <p className="text-gray-400 text-sm mb-2">视频描述</p>
            <p className="text-gray-200">{video.description}</p>
          </div>
        )}

        {/* 文字稿内容 */}
        {video.transcript ? (
          <div className="bg-gray-900 rounded-lg p-8 mb-8">
            <h2 className="text-2xl font-bold mb-6">识别文字稿</h2>

            {/* 完整文本 */}
            <div className="space-y-4">
              <p className="text-gray-200 leading-loose text-base whitespace-pre-wrap">
                {video.transcript.text}
              </p>
            </div>

            {/* 分段信息（如果有） */}
            {video.transcript.segments && video.transcript.segments.length > 0 && (
              <div className="mt-8 pt-8 border-t border-gray-800">
                <h3 className="text-xl font-bold mb-4">分段详情</h3>
                <div className="space-y-3">
                  {video.transcript.segments.map((segment, index) => (
                    <div key={index} className="flex gap-4 text-sm">
                      <span className="text-gray-500 whitespace-nowrap">
                        [{formatTime(segment.start_time)} - {formatTime(segment.end_time)}]
                      </span>
                      <span className="text-gray-300 flex-1">
                        {segment.text}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-gray-900 rounded-lg p-8 mb-8">
            <p className="text-gray-400">暂无文字稿</p>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex gap-4">
          <Link
            href="/modules/douyin"
            className="px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
          >
            返回列表
          </Link>
        </div>
      </div>
    </main>
  );
}
