export default function HomePage() {
  return (
    <main className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-4">个人资讯网站</h1>
        <p className="text-gray-400 mb-8">
          宏观经济数据、新闻联播分析、抖音视频文字稿
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <a
            href="/modules/news"
            className="p-6 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
            <h2 className="text-xl font-bold mb-2">新闻联播分析</h2>
            <p className="text-gray-400">政策推荐指数、板块影响分析</p>
          </a>

          <a
            href="/modules/economic"
            className="p-6 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
            <h2 className="text-xl font-bold mb-2">宏观经济数据</h2>
            <p className="text-gray-400">汇率、美债收益率、GDP数据</p>
          </a>

          <a
            href="/modules/douyin"
            className="p-6 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
            <h2 className="text-xl font-bold mb-2">抖音视频文字稿</h2>
            <p className="text-gray-400">财经博主视频转文字稿</p>
          </a>
        </div>
      </div>
    </main>
  );
}
