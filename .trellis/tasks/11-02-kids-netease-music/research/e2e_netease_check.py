"""真实网络端到端验证：网易云歌单 → 解析 → 预检 → 下载 → 落盘 → 设备歌单候选。

一次性脚本，不进测试套件（测试套件不依赖网络）。
从 backend/kids-catalog 目录运行：uv run python <此脚本路径>
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

# 脚本放在 .trellis/tasks/.../research/ 下，运行时需把后端包目录放进 sys.path。
PKG_ROOT = Path(__file__).resolve().parents[4] / "backend" / "kids-catalog"
sys.path.insert(0, str(PKG_ROOT))

from src.downloader import Downloader
from src.link_import import parse_album_link, probe_album

PLAYLIST_URL = "https://music.163.com/playlist?id=13907752641"
# 真实儿童专辑（实测 6 首可下载 + 2 首 VIP），避免 742 首的大专辑拖垮验证。
ALBUM_URL = "https://music.163.com/album?id=164558809"


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="netease-e2e-"))
    downloader = Downloader(workdir / "music", throttle_seconds=0.2, page_pause_seconds=0.2)
    failures = []
    try:
        for url, expect_platform in [(PLAYLIST_URL, "网易云歌单"), (ALBUM_URL, "网易云专辑")]:
            print(f"\n=== {url}")
            platform, album_id = parse_album_link(url)
            assert platform == expect_platform, (platform, expect_platform)
            print(f"  解析: {platform} / {album_id}")

            info = probe_album(platform, album_id)
            print(f"  预检: 标题={info['title']!r} 曲目数={info['track_count']} "
                  f"sale_type={info['sale_type']}")

            report = downloader.download_album(platform, album_id, info["title"])
            print(f"  下载: 成功 {report.downloaded} / 跳过 {report.skipped} / 失败 {report.failed}")
            if report.skip_reasons:
                print(f"  跳过原因示例: {report.skip_reasons[0]}")
            print(f"  汇总: {report.skip_summary()[:120]}")

            folder = downloader.album_dir(platform, info["title"])
            files = sorted(p for p in folder.iterdir() if p.is_file())
            print(f"  落盘目录: {folder.name!r}")
            print(f"  落盘: {len(files)} 个文件, 目录大小 {report.size_bytes} 字节")
            if files:
                head = files[0].read_bytes()[:3]
                print(f"  首个文件: {files[0].name} magic={head!r}")
                if head not in (b"ID3",) and b"ftyp" not in files[0].read_bytes()[:12]:
                    failures.append(f"{info['title']}: 首文件不是合法 mp3/m4a")

            # 校验可被现有设备合集扫描识别
            audio = [p for p in files if p.suffix.lower() in (".mp3", ".m4a")]
            if len(audio) != report.downloaded:
                failures.append(f"{info['title']}: 落盘数 {len(audio)} != 报告成功数 {report.downloaded}")

            # 重复下载应幂等（已存在文件不重复下载）
            again = downloader.download_album(platform, album_id, info["title"])
            print(f"  重跑: 成功 {again.downloaded}（应等于首轮，文件已存在）")
            if again.downloaded != report.downloaded:
                failures.append(f"{info['title']}: 重跑结果不一致")

        print("\n" + ("FAILED:\n  " + "\n  ".join(failures) if failures else "全部通过"))
        return 1 if failures else 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
