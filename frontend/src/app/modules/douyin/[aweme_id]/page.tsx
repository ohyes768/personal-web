"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080';

interface VideoDetail {
  aweme_id: string;
  success: boolean;
  error_message: string;
  info?: {
    title: string;
    author: string;
    create_time: string;
    share_url: string;
  };
  transcript?: {
    formatted_text: string;
    text: string;
    audio_duration: number;
    confidence: number;
  };
}

interface VideoDetailResponse {
  video: VideoDetail;
  exists: boolean;
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

        const data: VideoDetailResponse = await response.json();

        if (!data.exists) {
          throw new Error("视频不存在");
        }

        setVideo(data.video);
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

  const formatCreateTime = (timestamp: number) => {
    if (!timestamp) return "未知";
    return new Date(timestamp * 1000).toLocaleString("zh-CN");
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

  // 解析格式化文本，提取纯段落内容
  const parseFormattedText = (text: string): string[] => {
    if (!text) return [];

    const lines = text.split('\n');
    const paragraphs: string[] = [];
    let currentParagraph = '';

    for (const line of lines) {
      // 跳过分隔线
      if (line.includes('====')) continue;

      // 跳过时间范围和段落编号标记
      if (line.match(/^\[\d{2}:\d{2}-\d{2}:\d{2}\]/)) continue;
      if (line.match(/^第\s*\d+\s*段$/)) continue;

      // 如果是空行且当前段落有内容，保存段落
      if (line.trim() === '') {
        if (currentParagraph.trim()) {
          paragraphs.push(currentParagraph.trim());
          currentParagraph = '';
        }
        continue;
      }

      // 累积行内容
      currentParagraph += (currentParagraph ? ' ' : '') + line.trim();
    }

    // 保存最后一个段落
    if (currentParagraph.trim()) {
      paragraphs.push(currentParagraph.trim());
    }

    return paragraphs;
  };

  // 获取标题和作者
  const title = video.info?.title || "";
  const author = video.info?.author || "";
  const createTime = video.info?.create_time || "";
  const shareUrl = video.info?.share_url || "";

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
          {title}
        </h1>

        {/* 视频信息 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8 p-6 bg-gray-900 rounded-lg">
          <div>
            <p className="text-gray-400 text-sm mb-1">作者</p>
            <p className="text-lg">{author}</p>
          </div>
          <div>
            <p className="text-gray-400 text-sm mb-1">创建时间</p>
            <p className="text-lg">{createTime}</p>
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

        {/* 文字稿内容 */}
        {video.transcript ? (
          <div className="bg-gray-900 rounded-lg p-8 mb-8">
            <h2 className="text-2xl font-bold mb-6">识别文字稿</h2>

            {/* 识别内容 - 按段落显示 */}
            <div className="space-y-4">
              {parseFormattedText(video.transcript.formatted_text || video.transcript.text).map((paragraph, index) => (
                <p key={index} className="text-gray-200 leading-loose text-base">
                  {paragraph}
                </p>
              ))}
            </div>
          </div>
        ) : (
          <div className="bg-gray-900 rounded-lg p-8 mb-8">
            <p className="text-gray-400">暂无文字稿</p>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex gap-4">
          {shareUrl && (
            <a
              href={shareUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
            >
              在抖音中打开
            </a>
          )}
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
